"""
Node type registry mapping local-id to metadata.

This registry provides a complete mapping of Appian process model
node type identifiers to human-readable names and categories.

The registry is based on analysis of Appian's codebase, specifically:
- BuiltInNodesUuid.java
- palette-config.xml
"""

from dataclasses import dataclass
from typing import Dict, Optional

from appian_parser.domain.node_types.categories import NodeCategory


@dataclass(frozen=True)
class NodeTypeInfo:
    """
    Immutable node type information.

    Attributes:
        local_id: The Appian local-id identifier (e.g., 'core.0')
        name: Human-readable name (e.g., 'Start Event')
        category: Node category for grouping
        has_form: Whether this node type can have a SAIL form
        has_gateway_conditions: Whether this node type has gateway conditions
        has_pre_triggers: Whether this node type has pre-trigger rules
        has_subprocess_target: Whether this node type references a subprocess

    Example:
        >>> info = NodeTypeInfo('core.0', 'Start Event', NodeCategory.CORE)
        >>> info.name
        'Start Event'
        >>> info.category
        <NodeCategory.CORE: 'Core'>
    """
    local_id: str
    name: str
    category: NodeCategory
    has_form: bool = False
    has_gateway_conditions: bool = False
    has_pre_triggers: bool = False
    has_subprocess_target: bool = False


def infer_category_from_local_id(local_id: Optional[str]) -> NodeCategory:
    """
    Infer category from local-id pattern when not in registry.

    This function provides fallback categorization for node types
    not explicitly defined in the registry, based on naming patterns.

    Patterns:
        - core.X          -> Core/Gateway/Event (based on number)
        - internal.X      -> Activity
        - internal2.X     -> Smart Service
        - internal3.X     -> Smart Service
        - appian.system.smart-services.X -> Smart Service
        - appian.integration.X -> Integration
        - com.appiancorp.X -> Plugin
        - Other           -> Plugin

    Args:
        local_id: The node type local-id

    Returns:
        Inferred NodeCategory

    Example:
        >>> infer_category_from_local_id('core.0')
        <NodeCategory.CORE: 'Core'>
        >>> infer_category_from_local_id('internal3.custom_node')
        <NodeCategory.SMART_SERVICE: 'Smart Service'>
    """
    if not local_id:
        return NodeCategory.UNKNOWN

    if local_id.startswith('core.'):
        parts = local_id.split('.')
        if len(parts) > 1:
            num = parts[1]
            if num in ('0', '1'):
                return NodeCategory.CORE
            elif num in ('2', '3', '4', '5'):
                return NodeCategory.GATEWAY
            elif num in ('6', '7'):
                return NodeCategory.EVENT
        return NodeCategory.CORE
    elif local_id.startswith('internal.'):
        return NodeCategory.ACTIVITY
    elif local_id.startswith('internal2.'):
        return NodeCategory.SMART_SERVICE
    elif local_id.startswith('internal3.'):
        return NodeCategory.SMART_SERVICE
    elif local_id.startswith('appian.system.smart-services.'):
        return NodeCategory.SMART_SERVICE
    elif local_id.startswith('appian.integration.'):
        return NodeCategory.INTEGRATION
    elif local_id.startswith('com.appiancorp.'):
        return NodeCategory.PLUGIN
    else:
        return NodeCategory.PLUGIN


def get_node_type_info(local_id: str) -> NodeTypeInfo:
    """
    Get node type info from registry or create from inference.

    This function first checks the registry for an exact match.
    If not found, it creates a NodeTypeInfo with the local_id as
    the name and an inferred category.

    Args:
        local_id: The node type local-id

    Returns:
        NodeTypeInfo with name and category

    Example:
        >>> info = get_node_type_info('core.0')
        >>> info.name
        'Start Event'
        >>> info = get_node_type_info('custom.unknown.type')
        >>> info.name
        'custom.unknown.type'
        >>> info.category
        <NodeCategory.PLUGIN: 'Plugin'>
    """
    if local_id in NODE_TYPE_REGISTRY:
        return NODE_TYPE_REGISTRY[local_id]

    # Infer for unknown types
    return NodeTypeInfo(
        local_id=local_id,
        name=local_id,  # Use raw local-id as name
        category=infer_category_from_local_id(local_id)
    )


# Complete node type registry
# Source: Appian codebase analysis (BuiltInNodesUuid.java, palette-config.xml)
NODE_TYPE_REGISTRY: Dict[str, NodeTypeInfo] = {
    # =========================================================================
    # Core BPMN Nodes
    # =========================================================================
    'core.0': NodeTypeInfo('core.0', 'Start Event', NodeCategory.CORE),
    'core.1': NodeTypeInfo('core.1', 'End Event', NodeCategory.CORE),
    'core.2': NodeTypeInfo('core.2', 'AND Gateway', NodeCategory.GATEWAY),
    'core.3': NodeTypeInfo(
        'core.3', 'OR Gateway', NodeCategory.GATEWAY,
        has_gateway_conditions=True
    ),
    'core.4': NodeTypeInfo(
        'core.4', 'XOR Gateway', NodeCategory.GATEWAY,
        has_gateway_conditions=True
    ),
    'core.5': NodeTypeInfo(
        'core.5', 'Complex Gateway', NodeCategory.GATEWAY,
        has_gateway_conditions=True
    ),
    'core.6': NodeTypeInfo('core.6', 'Send Message', NodeCategory.EVENT),
    'core.7': NodeTypeInfo(
        'core.7', 'Timer/Rule/Receive Message', NodeCategory.EVENT,
        has_pre_triggers=True
    ),

    # =========================================================================
    # Basic Activities
    # =========================================================================
    'internal.16': NodeTypeInfo(
        'internal.16', 'Script Task', NodeCategory.ACTIVITY
    ),
    'internal.17': NodeTypeInfo(
        'internal.17', 'User Input Task', NodeCategory.HUMAN_TASK,
        has_form=True
    ),
    'internal.38': NodeTypeInfo(
        'internal.38', 'Subprocess', NodeCategory.ACTIVITY,
        has_subprocess_target=True
    ),
    'internal.39': NodeTypeInfo(
        'internal.39', 'Link Process', NodeCategory.ACTIVITY,
        has_subprocess_target=True
    ),

    # =========================================================================
    # Data Services
    # =========================================================================
    'internal3.write_records_to_source_23r3': NodeTypeInfo(
        'internal3.write_records_to_source_23r3', 'Write Records',
        NodeCategory.DATA_SERVICES
    ),
    'internal3.delete_records_from_source_23r4': NodeTypeInfo(
        'internal3.delete_records_from_source_23r4', 'Delete Records',
        NodeCategory.DATA_SERVICES
    ),
    'internal3.sync_records_from_source': NodeTypeInfo(
        'internal3.sync_records_from_source', 'Sync Records',
        NodeCategory.DATA_SERVICES
    ),
    'internal3.execute_stored_procedure': NodeTypeInfo(
        'internal3.execute_stored_procedure', 'Execute Stored Procedure',
        NodeCategory.DATA_SERVICES
    ),
    'internal.database601': NodeTypeInfo(
        'internal.database601', 'Query Database',
        NodeCategory.DATA_SERVICES
    ),
    'appian.system.smart-services.write-to-data-store': NodeTypeInfo(
        'appian.system.smart-services.write-to-data-store',
        'Write to Data Store Entity', NodeCategory.DATA_SERVICES
    ),
    'appian.system.smart-services.multi-write-to-data-store': NodeTypeInfo(
        'appian.system.smart-services.multi-write-to-data-store',
        'Write to Multiple DSE', NodeCategory.DATA_SERVICES
    ),
    'appian.system.smart-services.delete-from-data-store': NodeTypeInfo(
        'appian.system.smart-services.delete-from-data-store',
        'Delete from Data Store', NodeCategory.DATA_SERVICES
    ),

    # =========================================================================
    # Integration & APIs
    # =========================================================================
    'internal3.integration': NodeTypeInfo(
        'internal3.integration', 'Call Integration', NodeCategory.INTEGRATION
    ),
    'internal.webservices3': NodeTypeInfo(
        'internal.webservices3', 'Call Web Service', NodeCategory.INTEGRATION
    ),

    # =========================================================================
    # Document Management
    # =========================================================================
    'internal2.deletedocument': NodeTypeInfo(
        'internal2.deletedocument', 'Delete Document',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal2.movedocument': NodeTypeInfo(
        'internal2.movedocument', 'Move Document',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal2.movefolder': NodeTypeInfo(
        'internal2.movefolder', 'Move Folder',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal2.lockdocument': NodeTypeInfo(
        'internal2.lockdocument', 'Lock Document',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal2.unlockdocument': NodeTypeInfo(
        'internal2.unlockdocument', 'Unlock Document',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal2.updatedocument': NodeTypeInfo(
        'internal2.updatedocument', 'Edit Document Properties',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal2.deletefolder': NodeTypeInfo(
        'internal2.deletefolder', 'Delete Folder',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal2.renamefolder': NodeTypeInfo(
        'internal2.renamefolder', 'Rename Folder',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal.9': NodeTypeInfo(
        'internal.9', 'Create Folder', NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal.50': NodeTypeInfo(
        'internal.50', 'Create Knowledge Center',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal2.deletekc': NodeTypeInfo(
        'internal2.deletekc', 'Delete Knowledge Center',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal2.updatekc': NodeTypeInfo(
        'internal2.updatekc', 'Edit KC Properties',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal3.foldersecurity': NodeTypeInfo(
        'internal3.foldersecurity', 'Modify Folder Security',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal3.kcsecurity': NodeTypeInfo(
        'internal3.kcsecurity', 'Modify KC Security',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),

    # =========================================================================
    # Identity Management
    # =========================================================================
    'internal.19': NodeTypeInfo(
        'internal.19', 'Add Group Members', NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal.20': NodeTypeInfo(
        'internal.20', 'Add Group Admins', NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal3.addUserMaybePassword': NodeTypeInfo(
        'internal3.addUserMaybePassword', 'Create User',
        NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal3.createGroup': NodeTypeInfo(
        'internal3.createGroup', 'Create Group',
        NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal3.editGroup': NodeTypeInfo(
        'internal3.editGroup', 'Edit Group', NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal2.deletegroup': NodeTypeInfo(
        'internal2.deletegroup', 'Delete Group',
        NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal2.deactivateuser': NodeTypeInfo(
        'internal2.deactivateuser', 'Deactivate User',
        NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal3.reactivateuser': NodeTypeInfo(
        'internal3.reactivateuser', 'Reactivate User',
        NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal2.changeusertype': NodeTypeInfo(
        'internal2.changeusertype', 'Change User Type',
        NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal3.updateuserprofile4': NodeTypeInfo(
        'internal3.updateuserprofile4', 'Update User Profile',
        NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal2.joingroup': NodeTypeInfo(
        'internal2.joingroup', 'Join Group', NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal2.leavegroup': NodeTypeInfo(
        'internal2.leavegroup', 'Leave Group', NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal2.removegroupadmins': NodeTypeInfo(
        'internal2.removegroupadmins', 'Remove Group Admins',
        NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal2.removegroupmembers': NodeTypeInfo(
        'internal2.removegroupmembers', 'Remove Group Members',
        NodeCategory.IDENTITY_MANAGEMENT
    ),
    'internal.setgroupattr': NodeTypeInfo(
        'internal.setgroupattr', 'Set Group Attributes',
        NodeCategory.IDENTITY_MANAGEMENT
    ),

    # =========================================================================
    # Process Management
    # =========================================================================
    'appian.system.smart-services.start-process-4': NodeTypeInfo(
        'appian.system.smart-services.start-process-4', 'Start Process',
        NodeCategory.PROCESS_MANAGEMENT
    ),
    'appian.system.smart-services.start-process-2': NodeTypeInfo(
        'appian.system.smart-services.start-process-2', 'Start Process (v2)',
        NodeCategory.PROCESS_MANAGEMENT
    ),
    'appian.system.smart-services.cancel-process-2': NodeTypeInfo(
        'appian.system.smart-services.cancel-process-2', 'Cancel Process',
        NodeCategory.PROCESS_MANAGEMENT
    ),
    'appian.system.smart-services.complete-task-2': NodeTypeInfo(
        'appian.system.smart-services.complete-task-2', 'Complete Task',
        NodeCategory.PROCESS_MANAGEMENT
    ),
    'internal.45': NodeTypeInfo(
        'internal.45', 'Modify Process Security',
        NodeCategory.PROCESS_MANAGEMENT
    ),

    # =========================================================================
    # Communication
    # =========================================================================
    'internal3.sendemail3': NodeTypeInfo(
        'internal3.sendemail3', 'Send E-Mail', NodeCategory.COMMUNICATION
    ),
    'appian.system.smart-services.send-push-notification': NodeTypeInfo(
        'appian.system.smart-services.send-push-notification',
        'Send Push Notification', NodeCategory.COMMUNICATION
    ),

    # =========================================================================
    # AI Skills
    # =========================================================================
    'internal3.rs2_ai_skill_generative_ai2': NodeTypeInfo(
        'internal3.rs2_ai_skill_generative_ai2', 'Execute Generative AI Skill',
        NodeCategory.AI_SKILLS
    ),
    'internal3.rs2_ai_skill_document_classification3': NodeTypeInfo(
        'internal3.rs2_ai_skill_document_classification3', 'Classify Documents',
        NodeCategory.AI_SKILLS
    ),
    'internal3.rs2_ai_skill_document_extraction23r4': NodeTypeInfo(
        'internal3.rs2_ai_skill_document_extraction23r4', 'Extract from Document',
        NodeCategory.AI_SKILLS
    ),
    'internal3.rs2_ai_skill_email_classification2': NodeTypeInfo(
        'internal3.rs2_ai_skill_email_classification2', 'Classify Emails',
        NodeCategory.AI_SKILLS
    ),

    # =========================================================================
    # Document Generation
    # =========================================================================
    'internal.docxtemplatemerge': NodeTypeInfo(
        'internal.docxtemplatemerge', 'MS Word 2007 Doc from Template',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal.htmltemplatemerge601': NodeTypeInfo(
        'internal.htmltemplatemerge601', 'HTML Doc from Template',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal.pdftemplatemerge601': NodeTypeInfo(
        'internal.pdftemplatemerge601', 'PDF Doc from Template',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal.texttemplatemerge601': NodeTypeInfo(
        'internal.texttemplatemerge601', 'Text Doc from Template',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'internal.odttemplatemerge': NodeTypeInfo(
        'internal.odttemplatemerge', 'Open Office Writer Doc from Template',
        NodeCategory.DOCUMENT_MANAGEMENT
    ),
    'appian.system.smart-services.data-export-entity-csv2': NodeTypeInfo(
        'appian.system.smart-services.data-export-entity-csv2',
        'Export DSE to CSV', NodeCategory.DATA_SERVICES
    ),
    'appian.system.smart-services.data-export-entity-excel2': NodeTypeInfo(
        'appian.system.smart-services.data-export-entity-excel2',
        'Export DSE to Excel', NodeCategory.DATA_SERVICES
    ),

    # =========================================================================
    # Business Rules
    # =========================================================================
    'appian.system.smart-services.constant-increment': NodeTypeInfo(
        'appian.system.smart-services.constant-increment',
        'Increment Constant', NodeCategory.SMART_SERVICE
    ),
    'appian.system.smart-services.constant-update-2': NodeTypeInfo(
        'appian.system.smart-services.constant-update-2',
        'Update Constant', NodeCategory.SMART_SERVICE
    ),

    # =========================================================================
    # Analytics
    # =========================================================================
    'internal3.getreportdata601': NodeTypeInfo(
        'internal3.getreportdata601', 'Execute Process Report',
        NodeCategory.ANALYTICS
    ),

    # =========================================================================
    # Social
    # =========================================================================
    'appian.system.smart-services.follow-users': NodeTypeInfo(
        'appian.system.smart-services.follow-users', 'Follow Users',
        NodeCategory.SOCIAL
    ),
    'appian.system.smart-services.follow-records': NodeTypeInfo(
        'appian.system.smart-services.follow-records', 'Follow Records',
        NodeCategory.SOCIAL
    ),
    'appian.system.smart-services.publish-to-feed-5': NodeTypeInfo(
        'appian.system.smart-services.publish-to-feed-5',
        'Post Event to Feed', NodeCategory.SOCIAL
    ),
    'appian.system.smart-services.post-comment-to-feed-2': NodeTypeInfo(
        'appian.system.smart-services.post-comment-to-feed-2',
        'Post Comment to Feed', NodeCategory.SOCIAL
    ),

    # =========================================================================
    # Test Management
    # =========================================================================
    'appian.system.smart-services.start-system-test-2': NodeTypeInfo(
        'appian.system.smart-services.start-system-test-2',
        'Start Rule Tests (All)', NodeCategory.TEST_MANAGEMENT
    ),
    'appian.system.smart-services.start-app-test': NodeTypeInfo(
        'appian.system.smart-services.start-app-test',
        'Start Rule Tests (Applications)', NodeCategory.TEST_MANAGEMENT
    ),

    # =========================================================================
    # RPA
    # =========================================================================
    'internal3.exec_robotic_process2': NodeTypeInfo(
        'internal3.exec_robotic_process2', 'Execute Robotic Process',
        NodeCategory.RPA
    ),
    'internal3.rs2_robotic_task_remote_smart_service': NodeTypeInfo(
        'internal3.rs2_robotic_task_remote_smart_service',
        'Execute Robotic Task', NodeCategory.RPA
    ),
}
