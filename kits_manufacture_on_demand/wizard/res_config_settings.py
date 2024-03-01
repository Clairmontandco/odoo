from odoo import fields, models , api

class res_config_settings(models.TransientModel):
    _inherit = 'res.config.settings'

            
    create_production = fields.Boolean('Create Order Wise Manufacturing Order',config_parameter = 'kits_manufacture_on_demand.create_production')
    create_separate_production = fields.Boolean('Create Separate Manufacturing Order For Same Product',config_parameter = 'kits_manufacture_on_demand.create_separate_production')

    @api.onchange('create_separate_production')
    def auto_check_button_create_production(self):
        if self.create_separate_production == True:
            self.create_production = True

    @api.onchange('create_production')
    def auto_ucheck_button_create_separate_production(self):
        if self.create_production == False:
            self.create_separate_production = False

