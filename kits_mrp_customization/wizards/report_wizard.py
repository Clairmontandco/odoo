from odoo import _, api, fields, models, tools

class ReportWizard(models.TransientModel):
    _name = 'report.wizard'
    _description = 'Report Wizard'

    file = fields.Binary('File')