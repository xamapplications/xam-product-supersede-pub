{
    'name': 'Product Supersession Management',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Manage product supersession chains, interchangeable parts, and bidirectional relationships',
    'description': """
Product Supersession Management
===============================
This module provides a robust framework for managing product life cycles in inventory.

Key Features:
-------------
* **Bidirectional Relationships**: Automatically create reverse links (e.g., A supersedes B, so B is superseded by A).
* **Interchangeable Parts**: Define products that can be used interchangeably.
* **Full-Width Grid**: Seamlessly integrated into the Product Template view for easy management.
* **History Tracking**: Full chatter support to track changes in relationships.
* **Effective Dates**: Manage when relationships become active or expire.
    """,
    'author': 'XAM',
    'website': 'https://www.xam-apps.com',
    'license': 'LGPL-3',
    'depends': ['stock', 'product', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_supersede_views.xml',
        'views/product_template_views.xml',
    ],
    'images': ['static/description/icon.png', 'static/description/banner.png',],
    'installable': True,
    'application': True,
    'price': 1500.00,
    'currency': 'USD',
}
