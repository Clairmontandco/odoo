from odoo import models,api,fields,_
from odoo.exceptions import UserError, ValidationError
class AccountMoveLine(models.Model):
    _inherit='account.move.line'

    kcash_product = fields.Boolean(string='K-Cash Product',compute="_compute_kcash_product")   

    @api.onchange('product_id')
    def _compute_kcash_product(self):
        for rec in self:
            if rec.product_id.is_kcash_rewards:
                rec.kcash_product = True
            else:
                rec.kcash_product = False

    def unlink(self):
        for rec in self:
            if rec.kcash_product:
                if rec.price_unit == 0:
                    return super(AccountMoveLine, rec).unlink()
                else:
                    raise UserError(_('Sorry you can not remove line with kcash reward.'))
        return super(AccountMoveLine, self).unlink()
