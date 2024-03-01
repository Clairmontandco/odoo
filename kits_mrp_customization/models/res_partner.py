from odoo import api,_,fields,models

class res_partner(models.Model):
    _inherit='res.partner'

    kcash_bonus_ids = fields.One2many('kcash.bonus','partner_id','Clairmont Cash Bonus')
    kcash_balance = fields.Float('Clairmont Cash Balance',compute="_compute_kcash_balance",store=True)
    is_duplicate = fields.Boolean('Is Duplicate')
    checked_duplicate = fields.Boolean('Checked Duplicate')

    @api.depends('kcash_bonus_ids')
    def _compute_kcash_balance(self):
        for rec in self:
            kcash_rec = rec.kcash_bonus_ids.filtered(lambda x:x.partner_id.id == rec.id and x.expiry_date >= fields.Date.today() and not x.reward_fullfill)
            bal = sum(kcash_rec.mapped('credit'))
            bal -= sum(kcash_rec.mapped('debit'))
            rec.kcash_balance = bal
        
    def action_kcash_balance(self):
        pass

    def action_partner_marks_as_not_duplicate(self):
        for rec in self:
            rec.is_duplicate = False

    
      