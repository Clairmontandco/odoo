{
    "name": "Python Script Runner",
    "description": """
    Installing this module, user will able to run python code from Odoo.
""",
    "version": "15.0.0.1",
    'author': 'Keypress',
    'license': 'AGPL-3',
    'website': 'https://www.keypress.co.in',
    "depends": ['base'],
    "data": [
        'security/ir.model.access.csv',
        'views/python_script_runner_view.xml',
    ],
    "demo_xml": [],
    "installable": True,
}
