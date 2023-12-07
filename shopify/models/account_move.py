from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    shopify_refund_id = fields.Char("Shopify Refund ID", copy=False, help="Refund ID of the Shopify.")