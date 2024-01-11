{
    'name': 'Shopify Extended',
    'version': '1.2',
    'category': 'Sales',
    'summary': 'Shopify Customization for Clairmont and Co. v15',

    'depends': ['shopify'],

    'data': [
        #Views
        'views/product_template.xml',
    ],

    'images': ['static/description/icon.png'],

    'author': 'Teqstars',
    'website': 'https://teqstars.com',
    'support': 'support@teqstars.com',
    'maintainer': 'Teqstars',

    "description": """
        * Use odoo's default sale line's product description instead of using Shopify.
        * Use store name instead of customer name. If there are no store names then we will use the customer name.
        * Use Faire Commission and Faire processing fee products instead of custom line products.
        """,

    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'OPL-1',
}
