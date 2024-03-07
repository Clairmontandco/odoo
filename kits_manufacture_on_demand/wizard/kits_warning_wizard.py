from odoo import fields, models

class kits_warning_wizard(models.TransientModel):
    _name = 'kits.warning.wizard'


    warning = fields.Text('Warning')