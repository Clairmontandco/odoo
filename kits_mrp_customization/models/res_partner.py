from odoo import api,_,fields,models

class res_partner(models.Model):
    _inherit='res.partner'

    kcash_bonus_ids = fields.One2many('kcash.bonus','partner_id','KCash Bonus')
    kcash_balance = fields.Float('KCash Balance',compute="_compute_kcash_balance",store=True)
    is_duplicate = fields.Boolean('Is Duplicate')

    @api.depends('kcash_bonus_ids')
    def _compute_kcash_balance(self):
        for rec in self:
            kcash_rec = rec.kcash_bonus_ids.search([('partner_id','=',rec.id),('expiry_date','>=',fields.Date.today()),('reward_fullfill','=',False)])
            bal = sum(kcash_rec.mapped('credit'))
            bal -= sum(kcash_rec.mapped('debit'))
            rec.kcash_balance = bal
        
    def action_kcash_balance(self):
        pass

    
      
