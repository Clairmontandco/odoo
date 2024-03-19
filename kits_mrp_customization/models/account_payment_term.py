from odoo import models, fields
class account_payment_term(models.Model):
    _inherit = 'account.payment.term'

    kits_paid = fields.Boolean('Use For Paid')

    _sql_constraints = [
        ('kits_paid_uniq', 'unique (kits_paid)', 'Please note that Use For Paid cannot be selected for more than one payment term.')
    ]