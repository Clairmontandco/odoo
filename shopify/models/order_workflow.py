from odoo import models, fields, api


class OrderWorkflowConfig(models.Model):
    _inherit = "order.workflow.config.ts"

    is_create_credit_note = fields.Boolean('Create Credit Note', default=True)
