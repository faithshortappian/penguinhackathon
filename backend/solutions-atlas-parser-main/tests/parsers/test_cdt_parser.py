"""Tests for CDT parser @Table (bound table) extraction."""

from appian_parser.parsers.cdt_parser import CDTParser


_XSD_WITH_TABLE = """<?xml version="1.0" encoding="UTF-8"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:test:ns">
  <xsd:complexType name="MyCdt">
    <xsd:annotation>
      <xsd:appinfo>@Table(name="MY_CDT_TABLE")</xsd:appinfo>
    </xsd:annotation>
    <xsd:sequence>
      <xsd:element name="id" type="xsd:int">
        <xsd:annotation><xsd:appinfo>@Id @Column(name="ID")</xsd:appinfo></xsd:annotation>
      </xsd:element>
    </xsd:sequence>
  </xsd:complexType>
</xsd:schema>
"""

_XSD_NO_TABLE = """<?xml version="1.0" encoding="UTF-8"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:test:ns">
  <xsd:complexType name="NoTableCdt">
    <xsd:sequence>
      <xsd:element name="id" type="xsd:int"/>
    </xsd:sequence>
  </xsd:complexType>
</xsd:schema>
"""


def _parse(tmp_path, xsd: str):
    p = tmp_path / "cdt.xsd"
    p.write_text(xsd, encoding="utf-8")
    return CDTParser().parse(str(p))


def test_extracts_bound_table(tmp_path):
    data = _parse(tmp_path, _XSD_WITH_TABLE)
    assert data['table'] == 'MY_CDT_TABLE'
    assert data['uuid'] == '{urn:test:ns}MyCdt'
    # existing @Column extraction still works
    assert data['fields'][0]['column_name'] == 'ID'


def test_table_none_when_annotation_absent(tmp_path):
    data = _parse(tmp_path, _XSD_NO_TABLE)
    assert data['table'] is None
