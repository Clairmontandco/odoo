from odoo import fields, models, api
from odoo.addons.shopify.models.payout import PAYOUT_TRANSACTION_TYPE


class ShopifyPayoutAccountConfig(models.Model):
    _name = 'shopify.payout.account.config'
    _description = 'Shopify Payout Account Config'

    mk_instance_id = fields.Many2one('mk.instance', string="Instance", ondelete="cascade")
    company_id = fields.Many2one('res.company', related="mk_instance_id.company_id", store=True, compute_sudo=True)
    account_id = fields.Many2one('account.account', string='Account', domain="[('deprecated', '=', False), ('company_id', '=', company_id)]")
    transaction_type = fields.Selection(PAYOUT_TRANSACTION_TYPE, help="The type of the resource leading to the transaction.", string="Transaction Type")

    _sql_constraints = [('unique_transaction_type', 'unique(transaction_type, mk_instance_id)', 'You cannot create multiple configuration for same transaction type.')]