"""
Node type categories for Appian process model nodes.

Categories are used to group and classify process model nodes
for display and filtering purposes. These categories align with
Appian's node palette organization.
"""

from enum import Enum


class NodeCategory(str, Enum):
    """
    Categories for process model node types.

    These categories align with Appian's node palette organization
    and provide meaningful groupings for UI display.

    Categories:
        CORE: Start/End events
        GATEWAY: Decision points (AND, OR, XOR, Complex)
        EVENT: Message and timer events
        ACTIVITY: Basic activities (Script Task, Subprocess)
        HUMAN_TASK: User interaction nodes
        SMART_SERVICE: Automated service nodes
        DATA_SERVICES: Database and data store operations
        INTEGRATION: External system integrations
        DOCUMENT_MANAGEMENT: Document and folder operations
        IDENTITY_MANAGEMENT: User and group management
        PROCESS_MANAGEMENT: Process control operations
        COMMUNICATION: Email and notifications
        AI_SKILLS: AI-powered operations
        ANALYTICS: Reporting and analytics
        SOCIAL: Social features (feeds, following)
        TEST_MANAGEMENT: Testing operations
        RPA: Robotic process automation
        PLUGIN: Custom/third-party plugins
        UNKNOWN: Unrecognized node types
    """
    CORE = "Core"
    GATEWAY = "Gateway"
    EVENT = "Event"
    ACTIVITY = "Activity"
    HUMAN_TASK = "Human Task"
    SMART_SERVICE = "Smart Service"
    DATA_SERVICES = "Data Services"
    INTEGRATION = "Integration"
    DOCUMENT_MANAGEMENT = "Document Management"
    IDENTITY_MANAGEMENT = "Identity Management"
    PROCESS_MANAGEMENT = "Process Management"
    COMMUNICATION = "Communication"
    AI_SKILLS = "AI Skills"
    ANALYTICS = "Analytics"
    SOCIAL = "Social"
    TEST_MANAGEMENT = "Test Management"
    RPA = "RPA"
    PLUGIN = "Plugin"
    UNKNOWN = "Unknown"
