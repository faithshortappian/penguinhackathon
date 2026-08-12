"""Tests for the schema module."""
import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from appian_parser.schema.ddl_replay_engine import DDLReplayEngine
from appian_parser.schema.models import Column, ForeignKey, SchemaResult, Table
from appian_parser.schema.schema_builder import SchemaBuilder
from appian_parser.schema.script_finder import ScriptFinder
from appian_parser.schema.statement_parser import StatementParser


# ─── StatementParser Tests ───────────────────────────────────────────────────


class TestStatementParser:
    """Tests for StatementParser."""

    def setup_method(self):
        self.parser = StatementParser()

    def test_simple_statements(self):
        sql = "CREATE TABLE t1 (id int);\nCREATE TABLE t2 (id int);"
        stmts = self.parser.parse(sql)
        assert len(stmts) == 2
        assert stmts[0].startswith("CREATE TABLE t1")
        assert stmts[1].startswith("CREATE TABLE t2")

    def test_strips_leading_comments(self):
        sql = "-- comment\n-- another\n\nCREATE TABLE t1 (id int);"
        stmts = self.parser.parse(sql)
        assert len(stmts) == 1
        assert stmts[0].startswith("CREATE TABLE")

    def test_strips_leading_empty_lines_before_comments(self):
        sql = "SELECT 1;\n\n\n-- comment\n-- another\n\nCREATE TABLE t1 (id int);"
        stmts = self.parser.parse(sql)
        assert len(stmts) == 2
        assert stmts[1].startswith("CREATE TABLE")

    def test_respects_quoted_semicolons(self):
        sql = "INSERT INTO t1 (name) VALUES ('hello; world');"
        stmts = self.parser.parse(sql)
        assert len(stmts) == 1
        assert "hello; world" in stmts[0]

    def test_extracts_from_delimiter_blocks(self):
        sql = """
DELIMITER $$
CREATE PROCEDURE test()
BEGIN
-- START SCRIPT CONTENT ---
CREATE TABLE t1 (id int);
-- END SCRIPT CONTENT ---
END $$
DELIMITER ;
"""
        stmts = self.parser.parse(sql)
        assert any("CREATE TABLE t1" in s for s in stmts)

    def test_multiple_script_content_blocks(self):
        sql = """
DELIMITER $$
CREATE PROCEDURE p1()
BEGIN
-- START SCRIPT CONTENT ---
CREATE TABLE t1 (id int);
-- END SCRIPT CONTENT ---
END $$
DELIMITER ;

DELIMITER $$
CREATE PROCEDURE p2()
BEGIN
-- START SCRIPT CONTENT ---
CREATE TABLE t2 (id int);
-- END SCRIPT CONTENT ---
END $$
DELIMITER ;
"""
        stmts = self.parser.parse(sql)
        creates = [s for s in stmts if s.upper().startswith("CREATE TABLE")]
        assert len(creates) == 2

    def test_top_level_statements_preserved(self):
        sql = """
CREATE TABLE framework (id int);

DELIMITER $$
CREATE PROCEDURE p1()
BEGIN
-- START SCRIPT CONTENT ---
CREATE TABLE t1 (id int);
-- END SCRIPT CONTENT ---
END $$
DELIMITER ;
"""
        stmts = self.parser.parse(sql)
        creates = [s for s in stmts if s.upper().startswith("CREATE TABLE")]
        assert len(creates) == 2

    def test_ignores_non_script_content_in_delimiter_blocks(self):
        sql = """
DELIMITER $$
CREATE PROCEDURE p1()
BEGIN
CALL some_function();
IF @cont > 0 THEN
-- START SCRIPT CONTENT ---
CREATE TABLE t1 (id int);
-- END SCRIPT CONTENT ---
CALL update_function();
END IF;
END $$
DELIMITER ;
"""
        stmts = self.parser.parse(sql)
        assert not any("CALL" in s for s in stmts if s.upper().startswith("CALL"))
        assert any("CREATE TABLE t1" in s for s in stmts)


# ─── DDLReplayEngine Tests ───────────────────────────────────────────────────


class TestDDLReplayEngine:
    """Tests for DDLReplayEngine."""

    def setup_method(self):
        self.engine = DDLReplayEngine()

    def test_create_table_basic(self):
        stmts = ["CREATE TABLE `t1` (`id` int(11) NOT NULL AUTO_INCREMENT, `name` varchar(255), PRIMARY KEY (`id`))"]
        self.engine.replay(stmts)
        tables = self.engine.get_tables()
        assert "t1" in tables
        assert "id" in tables["t1"].columns
        assert "name" in tables["t1"].columns
        assert tables["t1"].columns["id"].auto_increment is True
        assert tables["t1"].columns["id"].nullable is False
        assert tables["t1"].primary_key == ["id"]

    def test_create_table_if_not_exists(self):
        stmts = [
            "CREATE TABLE IF NOT EXISTS `t1` (`id` int(11))",
            "CREATE TABLE IF NOT EXISTS `t1` (`id` int(11), `extra` varchar(50))",
        ]
        self.engine.replay(stmts)
        tables = self.engine.get_tables()
        # Second CREATE should be skipped (IF NOT EXISTS)
        assert "extra" not in tables["t1"].columns

    def test_alter_table_add_column(self):
        stmts = [
            "CREATE TABLE `t1` (`id` int(11))",
            "ALTER TABLE `t1` ADD COLUMN `name` varchar(255) DEFAULT NULL",
        ]
        self.engine.replay(stmts)
        assert "name" in self.engine.get_tables()["t1"].columns
        assert self.engine.get_tables()["t1"].columns["name"].nullable is True

    def test_alter_table_modify_column(self):
        stmts = [
            "CREATE TABLE `t1` (`name` varchar(100))",
            "ALTER TABLE `t1` MODIFY COLUMN `name` varchar(255) NOT NULL",
        ]
        self.engine.replay(stmts)
        col = self.engine.get_tables()["t1"].columns["name"]
        assert col.data_type == "varchar(255)"
        assert col.nullable is False

    def test_alter_table_drop_column(self):
        stmts = [
            "CREATE TABLE `t1` (`id` int, `temp` varchar(50))",
            "ALTER TABLE `t1` DROP COLUMN `temp`",
        ]
        self.engine.replay(stmts)
        assert "temp" not in self.engine.get_tables()["t1"].columns

    def test_alter_table_add_foreign_key(self):
        stmts = [
            "CREATE TABLE `parent` (`id` int(11) PRIMARY KEY)",
            "CREATE TABLE `child` (`id` int, `parent_id` int)",
            "ALTER TABLE `child` ADD CONSTRAINT `fk_parent` FOREIGN KEY (`parent_id`) REFERENCES `parent` (`id`)",
        ]
        self.engine.replay(stmts)
        fks = self.engine.get_tables()["child"].foreign_keys
        assert len(fks) == 1
        assert fks[0].name == "fk_parent"
        assert fks[0].columns == ["parent_id"]
        assert fks[0].ref_table == "parent"

    def test_alter_table_drop_foreign_key(self):
        stmts = [
            "CREATE TABLE `parent` (`id` int(11) PRIMARY KEY)",
            "CREATE TABLE `child` (`id` int, `parent_id` int)",
            "ALTER TABLE `child` ADD CONSTRAINT `fk_parent` FOREIGN KEY (`parent_id`) REFERENCES `parent` (`id`)",
            "ALTER TABLE `child` DROP FOREIGN KEY `fk_parent`",
        ]
        self.engine.replay(stmts)
        assert len(self.engine.get_tables()["child"].foreign_keys) == 0

    def test_alter_table_rename_table(self):
        stmts = [
            "CREATE TABLE `old_name` (`id` int)",
            "ALTER TABLE `old_name` RENAME TO `new_name`",
        ]
        self.engine.replay(stmts)
        tables = self.engine.get_tables()
        assert "new_name" in tables
        assert "old_name" not in tables

    def test_alter_table_rename_column(self):
        stmts = [
            "CREATE TABLE `t1` (`old_col` int)",
            "ALTER TABLE `t1` RENAME COLUMN `old_col` TO `new_col`",
        ]
        self.engine.replay(stmts)
        cols = self.engine.get_tables()["t1"].columns
        assert "new_col" in cols
        assert "old_col" not in cols

    def test_multi_clause_alter_table(self):
        stmts = [
            "CREATE TABLE `parent` (`id` int PRIMARY KEY)",
            "CREATE TABLE `child` (`id` int, `status_id` int, `method_id` int)",
            "ALTER TABLE `child` ADD CONSTRAINT `fk_status` FOREIGN KEY (`status_id`) REFERENCES `parent` (`id`), ADD CONSTRAINT `fk_method` FOREIGN KEY (`method_id`) REFERENCES `parent` (`id`)",
        ]
        self.engine.replay(stmts)
        fks = self.engine.get_tables()["child"].foreign_keys
        assert len(fks) == 2

    def test_drop_table(self):
        stmts = [
            "CREATE TABLE `t1` (`id` int)",
            "DROP TABLE IF EXISTS `t1`",
        ]
        self.engine.replay(stmts)
        assert "t1" not in self.engine.get_tables()

    def test_insert_reference_data(self):
        stmts = [
            "CREATE TABLE `APP_R_DATA` (`id` int, `label` varchar(255), `type` varchar(100))",
            "INSERT INTO `APP_R_DATA` (`id`, `label`, `type`) VALUES (1, 'Active', 'Status'), (2, 'Inactive', 'Status')",
        ]
        self.engine.replay(stmts)
        ref = self.engine.get_reference_data()
        assert "APP_R_DATA" in ref
        assert len(ref["APP_R_DATA"]) == 2
        assert ref["APP_R_DATA"][0]["label"] == "Active"

    def test_insert_any_table_captured_as_reference(self):
        """Any table with INSERT statements is treated as reference data."""
        stmts = [
            "CREATE TABLE `APP_BUSINESS` (`id` int, `name` varchar(255))",
            "INSERT INTO `APP_BUSINESS` (`id`, `name`) VALUES (1, 'test')",
        ]
        self.engine.replay(stmts)
        ref = self.engine.get_reference_data()
        assert "APP_BUSINESS" in ref
        assert len(ref["APP_BUSINESS"]) == 1

    def test_update_reference_data(self):
        stmts = [
            "CREATE TABLE `APP_R_DATA` (`id` int, `label` varchar(255), `is_active` tinyint)",
            "INSERT INTO `APP_R_DATA` (`id`, `label`, `is_active`) VALUES (1, 'Test', 1)",
            "UPDATE `APP_R_DATA` SET `is_active` = 0 WHERE `id` = 1",
        ]
        self.engine.replay(stmts)
        ref = self.engine.get_reference_data()
        assert ref["APP_R_DATA"][0]["is_active"] == "0"

    def test_rename_resolves_in_fk(self):
        stmts = [
            "CREATE TABLE `old_parent` (`id` int PRIMARY KEY)",
            "CREATE TABLE `child` (`id` int, `parent_id` int)",
            "ALTER TABLE `old_parent` RENAME TO `new_parent`",
            "ALTER TABLE `child` ADD CONSTRAINT `fk` FOREIGN KEY (`parent_id`) REFERENCES `old_parent` (`id`)",
        ]
        self.engine.replay(stmts)
        fks = self.engine.get_tables()["child"].foreign_keys
        assert fks[0].ref_table == "new_parent"

    def test_insert_with_old_table_name_after_rename(self):
        stmts = [
            "CREATE TABLE `APP_R_OLD_NAME` (`id` int, `label` varchar(255))",
            "INSERT INTO `APP_R_OLD_NAME` (`id`, `label`) VALUES (1, 'test')",
            "ALTER TABLE `APP_R_OLD_NAME` RENAME TO `APP_R_NEW_NAME`",
        ]
        self.engine.replay(stmts)
        ref = self.engine.get_reference_data()
        assert "APP_R_NEW_NAME" in ref
        assert "APP_R_OLD_NAME" not in ref

    def test_add_column_with_after_clause(self):
        stmts = [
            "CREATE TABLE `t1` (`id` int, `name` varchar(255))",
            "ALTER TABLE `t1` ADD COLUMN `status` int DEFAULT NULL AFTER `id`",
        ]
        self.engine.replay(stmts)
        assert "status" in self.engine.get_tables()["t1"].columns

    def test_foreign_key_if_not_exists(self):
        stmts = [
            "CREATE TABLE `parent` (`id` int PRIMARY KEY)",
            "CREATE TABLE `child` (`id` int, `pid` int)",
            "ALTER TABLE `child` ADD CONSTRAINT `fk` FOREIGN KEY IF NOT EXISTS (`pid`) REFERENCES `parent` (`id`)",
        ]
        self.engine.replay(stmts)
        assert len(self.engine.get_tables()["child"].foreign_keys) == 1


# ─── ScriptFinder Tests ──────────────────────────────────────────────────────


class TestScriptFinder:
    """Tests for ScriptFinder."""

    def setup_method(self):
        self.finder = ScriptFinder()

    def test_finds_scripts_at_root(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "01.App.sql").write_text("SELECT 1;")
        result = self.finder.find_scripts(tmp_path)
        assert len(result) == 1
        assert result[0].name == "01.App.sql"

    def test_finds_scripts_nested_one_level(self, tmp_path):
        nested = tmp_path / "AppNamev1.0.0" / "scripts"
        nested.mkdir(parents=True)
        (nested / "01.App.sql").write_text("SELECT 1;")
        result = self.finder.find_scripts(tmp_path)
        assert len(result) == 1

    def test_returns_sorted_by_filename(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "03.App.sql").write_text("SELECT 3;")
        (scripts_dir / "01.App.sql").write_text("SELECT 1;")
        (scripts_dir / "02.App.sql").write_text("SELECT 2;")
        result = self.finder.find_scripts(tmp_path)
        assert [r.name for r in result] == ["01.App.sql", "02.App.sql", "03.App.sql"]

    def test_ignores_oracle_scripts(self, tmp_path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "01.App.sql").write_text("SELECT 1;")
        (tmp_path / "oracle-scripts").mkdir()
        (tmp_path / "oracle-scripts" / "01.App.sql").write_text("SELECT 1;")
        result = self.finder.find_scripts(tmp_path)
        assert len(result) == 1

    def test_returns_empty_when_no_scripts(self, tmp_path):
        result = self.finder.find_scripts(tmp_path)
        assert result == []


# ─── SchemaBuilder Tests ─────────────────────────────────────────────────────


class TestSchemaBuilder:
    """Tests for SchemaBuilder."""

    def setup_method(self):
        self.builder = SchemaBuilder()

    def test_returns_none_when_no_scripts(self, tmp_path):
        result = self.builder.build(tmp_path)
        assert result is None

    def test_builds_schema_from_simple_script(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        sql = """
CREATE TABLE `APP_R_STATUS` (`id` int PRIMARY KEY, `label` varchar(100));
INSERT INTO `APP_R_STATUS` (`id`, `label`) VALUES (1, 'Active'), (2, 'Inactive');
CREATE TABLE `APP_ENTITY` (`id` int PRIMARY KEY, `status_id` int);
ALTER TABLE `APP_ENTITY` ADD CONSTRAINT `fk_status` FOREIGN KEY (`status_id`) REFERENCES `APP_R_STATUS` (`id`);
"""
        (scripts_dir / "01.test.sql").write_text(sql)
        result = self.builder.build(tmp_path)

        assert result is not None
        assert len(result.tables) == 2
        assert len(result.relationships) == 1
        assert result.relationships[0]["from_table"] == "APP_ENTITY"
        assert result.relationships[0]["to_table"] == "APP_R_STATUS"
        assert "APP_R_STATUS" in result.reference_data
        assert len(result.reference_data["APP_R_STATUS"]) == 2

    def test_topological_order_parents_before_children(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        sql = """
CREATE TABLE `parent` (`id` int PRIMARY KEY);
CREATE TABLE `child` (`id` int, `parent_id` int);
ALTER TABLE `child` ADD CONSTRAINT `fk` FOREIGN KEY (`parent_id`) REFERENCES `parent` (`id`);
"""
        (scripts_dir / "01.test.sql").write_text(sql)
        result = self.builder.build(tmp_path)

        parent_idx = result.insertion_order.index("parent")
        child_idx = result.insertion_order.index("child")
        assert parent_idx < child_idx

    def test_table_classification(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        sql = """
CREATE TABLE `APP_ScriptExecutionHistory` (`id` int);
CREATE TABLE `APP_R_STATUS` (`id` int);
CREATE TABLE `APP_A_R_AUDIT` (`id` int);
CREATE TABLE `APP_TMG_TASK` (`id` int);
CREATE TABLE `APP_ENTITY` (`id` int);
"""
        (scripts_dir / "01.test.sql").write_text(sql)
        result = self.builder.build(tmp_path)

        assert result.table_classification["APP_ScriptExecutionHistory"] == "framework"
        assert result.table_classification["APP_R_STATUS"] == "reference"
        assert result.table_classification["APP_A_R_AUDIT"] == "audit"
        assert result.table_classification["APP_TMG_TASK"] == "task_management"
        assert result.table_classification["APP_ENTITY"] == "business"

    def test_multiple_script_files_processed_sequentially(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "01.test.sql").write_text("CREATE TABLE `t1` (`id` int);")
        (scripts_dir / "02.test.sql").write_text("CREATE TABLE `t2` (`id` int);")
        result = self.builder.build(tmp_path)
        assert len(result.tables) == 2

    def test_tables_as_dict_serialization(self, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        sql = "CREATE TABLE `t1` (`id` int(11) NOT NULL AUTO_INCREMENT, `name` varchar(255) DEFAULT 'test' COMMENT 'The name', PRIMARY KEY (`id`));"
        (scripts_dir / "01.test.sql").write_text(sql)
        result = self.builder.build(tmp_path)

        d = result.tables_as_dict()
        assert "t1" in d
        assert d["t1"]["primary_key"] == ["id"]
        assert d["t1"]["columns"]["id"]["type"] == "int(11)"
        assert d["t1"]["columns"]["id"]["auto_increment"] is True
        assert d["t1"]["columns"]["name"]["default"] == "test"
        assert d["t1"]["columns"]["name"]["comment"] == "The name"
        # Verify JSON serializable
        json.dumps(d)


# ─── Integration Test with Real Package ──────────────────────────────────────


class TestSchemaIntegration:
    """Integration tests using real package data."""

    PACKAGES_DIR = Path("/Users/ramaswamy.u/Documents/Backup/package-backup/packages")

    @pytest.fixture
    def source_selection_root(self, tmp_path):
        pkg = self.PACKAGES_DIR / "SourceSelection-latest.zip"
        if not pkg.exists():
            pytest.skip("Source Selection package not available")
        with zipfile.ZipFile(pkg) as zf:
            zf.extractall(tmp_path)
        return tmp_path

    def test_source_selection_full_parse(self, source_selection_root):
        builder = SchemaBuilder()
        result = builder.build(source_selection_root)

        assert result is not None
        assert result.summary["total_tables"] >= 80
        assert result.summary["total_foreign_keys"] >= 100
        assert result.summary["reference_data_rows"] >= 200

        # Verify key business table exists with expected columns
        assert "AS_GSS_EVALUATION" in result.tables
        eval_table = result.tables["AS_GSS_EVALUATION"]
        assert "EVALUATION_ID" in eval_table.columns
        assert "EVALUATION_STATUS_ID" in eval_table.columns
        assert eval_table.columns["EVALUATION_ID"].auto_increment is True

        # Verify FK relationships
        eval_fks = [r for r in result.relationships if r["from_table"] == "AS_GSS_EVALUATION"]
        assert len(eval_fks) >= 5

        # Verify reference data
        assert "AS_GSS_R_DATA" in result.reference_data
        r_data = result.reference_data["AS_GSS_R_DATA"]
        assert len(r_data) > 50  # Should have many reference data rows
        # Verify REF_TYPE column exists in the data
        assert any("REF_TYPE" in row for row in r_data)

        # Verify topological order (check for minimal violations — cycles are expected in real schemas)
        order_idx = {name: i for i, name in enumerate(result.insertion_order)}
        violations = 0
        for rel in result.relationships:
            parent = rel["to_table"]
            child = rel["from_table"]
            if parent in order_idx and child in order_idx and parent != child:
                if order_idx[parent] > order_idx[child]:
                    violations += 1
        # Allow a small number of violations due to circular FKs in real schemas
        assert violations <= 40, f"Too many topological violations: {violations}"

        # Verify JSON serializable
        d = result.tables_as_dict()
        json.dumps(d)
        json.dumps(result.relationships)
        json.dumps(result.reference_data)
