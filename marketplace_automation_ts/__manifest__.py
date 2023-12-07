{
    "name": "Marketplace Automation",
    "version": "1.7",
    "category": "Extra",
    "summary": "Base app for Marketplace Apps. Perform automation stuff for sale orders and Invoices.",

    "depends": ['account', 'stock', 'sale_management', 'base_marketplace'],

    'data': [
        'security/ir.model.access.csv',

        'views/order_workflow_view.xml',
        'views/sale_view.xml',

    ],

    'images': ['static/description/mk_automation.jpg'],

    "author": "Teqstars",
    "website": "https://teqstars.com",
    'support': 'support@teqstars.com',
    'maintainer': 'Teqstars',

    "description": """
        """,

    'demo': [],
    'license': 'OPL-1',
    'live_test_url': '',
    'auto_install': False,
    'installable': True,
    'application': False,
    'qweb': [],
    "price": "10.00",
    "currency": "EUR",
}
