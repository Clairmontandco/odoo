from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

class AddKCashRewardWizard(models.TransientModel):
    _name = 'add.kcash.reward.wizard'

    sale_id = fields.Many2one('sale.order','Order')
    partner_id = fields.Many2one('res.partner','Partner')
    expiry_date = fields.Date('Expiry Date',default=fields.Date.today())
    amount = fields.Float('Amount')
    kcash_type = fields.Selection([('reward','Reward'),('credit','Credit')],default='reward',string='Type')

    def action_process(self):
        for rec in self:
            available_reward = rec.partner_id.kcash_bonus_ids.filtered(lambda x:x.sale_id == rec.sale_id and x.kcash_type == 'reward') if rec.kcash_type == 'reward' else False
            if available_reward:
                raise UserError('Clairmont Cash Reward is already added !')
            else :
                self.env['kcash.bonus'].create({'sale_id':rec.sale_id.id,'partner_id':rec.partner_id.id,'credit':rec.amount,'expiry_date':rec.expiry_date,'kcash_type':rec.kcash_type})