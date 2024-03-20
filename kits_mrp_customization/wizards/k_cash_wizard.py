from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

class KCashWizard(models.TransientModel):
    _name = 'k.cash.wizard'
    _description = "Kcash wizard"

    sale_id = fields.Many2one('sale.order')
    kcash_id = fields.Many2one('kcash.bonus')
    amount = fields.Float(string="Clairmont Cash")
    available_kcash = fields.Float(string='Available Clairmont Cash')
    remain_kcash = fields.Float(string='Remaining Clairmont Cash')


    @api.onchange('amount')
    def onchange_amount(self):
        if self.amount:
            self.remain_kcash = self.available_kcash - self.amount
             
    def action_process(self):
        for rec in self:
            if self.amount <= 0:
                raise UserError(_('Please enter an amount greater than 0.'))
            if self.available_kcash < self.amount:
                raise UserError(_('Oops! You entered more than your Kcash balance. Please enter less or equal.'))
            else:
                db_amount = rec.amount
                line_ul = False
                product_obj = self.env['product.product']
                pro_id =  product_obj.search([('is_kcash_rewards','=',True)])
                kcash_pro_line = self.sale_id.order_line.search([('order_id','=',self.sale_id.id),('product_id','=',pro_id.id)])
                if kcash_pro_line and not line_ul:
                    line_ul = True
                    for kcs in self.sale_id.kcash_history_ids:
                        kcs.kcash_id.reward_fullfill = False
                        kcs.kcash_id.debit -= kcs.amount
                        kcs.unlink()
                    kcash_pro_line.price_unit = 0
                for kcb in self.sale_id.partner_id.kcash_bonus_ids:
                    if db_amount:
                        if kcb.expiry_date >= fields.Date.today() and not kcb.reward_fullfill:
                            if kcb.credit-kcb.debit  <= db_amount:
                                self.sale_id.kcash_id = kcb.id
                                db_amount -= kcb.credit-kcb.debit
                                kcb.debit+=kcb.credit-kcb.debit
                            elif kcb.credit-kcb.debit  >= db_amount:
                                self.sale_id.kcash_id = kcb.id
                                kcb.debit += db_amount
                                db_amount = 0
                            self.sale_id.write({
                                        "kcash_history_ids": [(0, 0, {
                                            "kcash_id": self.sale_id.kcash_id.id,
                                            'amount':kcb.debit,
                                            'order_id':self.sale_id.id
                                        })],
                                    })
                            if self.amount:
                                kcash_pro = self.sale_id.order_line.search([('order_id','=',self.sale_id.id),('product_id','=',pro_id.id)])
                                if kcash_pro:
                                    kcash_pro.price_unit = -abs(rec.amount)
                                    kcash_pro.kcash_product = True
                                else:
                                    if not pro_id:
                                        pro_id  = product_obj.create({
                                            'name':'Clairmont Cash Reward',
                                            'type':'service',
                                            'is_kcash_rewards':True
                                        })
                                    self.sale_id.write({
                                        "order_line": [(0, 0, {
                                            "product_id": pro_id.id,
                                            'price_unit':-abs(kcb.debit),
                                            'kcash_product': True,
                                        })],
                                    })
            rec.sale_id.partner_id._compute_kcash_balance()

