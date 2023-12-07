from .. import shopify
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError

_logger = logging.getLogger("Teqstars:Shopify")

WEBHOOK_EVENTS = [('customers/create', 'Create Customer'),
                  ('customers/update', 'Update Customer'),
                  ('orders/create', 'Create Orders'),
                  ('orders/updated', 'Update Orders'),
                  ('products/create', 'Create Product'),
                  ('products/update', 'Update Product'),
                  ('products/delete', 'Delete Product')]


class ShopifyWebhook(models.Model):
    _name = "shopify.webhook.ts"
    _description = "Shopify Webhook"

    name = fields.Char("Name", required=1)
    webhook_event = fields.Selection(WEBHOOK_EVENTS, "Webhook Event Type")
    webhook_id = fields.Char("Webhook ID", copy=False)
    active_webhook = fields.Boolean("Active", default=False)
    mk_instance_id = fields.Many2one('mk.instance', "Instance", ondelete='cascade')

    _sql_constraints = [('event_account_unique', 'unique(webhook_event,mk_instance_id)', 'You cannot create duplicate Webhook Events.')]

    def fetch_all_webhook_from_shopify(self, mk_instance_id):
        mk_instance_id.connection_to_shopify()
        webhooks = shopify.Webhook().find()
        for webhook in webhooks:
            webhook_dict = webhook.to_dict()
            webhook_id = webhook_dict.get('id')
            webhook_event = webhook_dict.get('topic')
            webhook_url = mk_instance_id.webhook_url
            if not webhook_url.endswith('/'):
                webhook_url = mk_instance_id.webhook_url + '/'
            if webhook_dict.get('address') != webhook_url:
                continue
            existing_webhook_id = self.search([('mk_instance_id', '=', mk_instance_id.id), '|', ('webhook_id', '=', webhook_id), ('webhook_event', '=', webhook_event)])
            if existing_webhook_id and not existing_webhook_id.active_webhook:
                existing_webhook_id.with_context(skip_create=True).write({'active_webhook': True})
            if not existing_webhook_id:
                create_vals = {'name': dict(self._fields['webhook_event'].selection).get(webhook_event),
                               'webhook_event': webhook_event,
                               'webhook_id': webhook_id,
                               'active_webhook': True,
                               'mk_instance_id': mk_instance_id.id}
                self.with_context(skip_create=True).create(create_vals)
        return True

    def create_webhook_in_shopify(self, vals, mk_instance_id):
        mk_instance_id.connection_to_shopify()
        if not mk_instance_id.webhook_url.startswith('https://'):
            raise ValidationError("You can only create Webhook with secure URL (https).")
        data_vals = {"topic": self.webhook_event, "address": mk_instance_id.webhook_url, "format": "json"}
        response = shopify.Webhook.create(data_vals)
        if response.id:
            response_dict = response.to_dict()
            webhook_id = response_dict.get('webhook', {}).get('id') or response_dict.get('id')
            vals.update({'webhook_id': webhook_id})
        if response.errors and response.errors.errors:
            raise ValidationError(_(response.errors.errors.get('address')))
        return vals

    @api.model
    def create(self, vals):
        res = super(ShopifyWebhook, self).create(vals)
        if vals.get('active_webhook') and not self.env.context.get('skip_create', False):
            mk_instance_id = self.env['mk.instance'].browse(vals.get('mk_instance_id'))
            res.create_webhook_in_shopify(vals, mk_instance_id)
        return res

    def write(self, vals):
        if vals.get('active_webhook') and not self.env.context.get('skip_create', False):
            self.create_webhook_in_shopify(vals, self.mk_instance_id)
        if 'active_webhook' in vals and vals.get('active_webhook') == False:
            try:
                self.mk_instance_id.connection_to_shopify()
                existing_shopify_events = shopify.Webhook().find(topic=self.webhook_event)
                for shopify_events in existing_shopify_events:
                    shopify_event_dict = shopify_events.to_dict()
                    webhook_address = shopify_event_dict.get('address', '') or ''
                    if webhook_address == self.mk_instance_id.webhook_url:
                        shopify_events.destroy()
            except Exception as err:
                _logger.error("SHOPIFY WEBHOOK WRITE: Cannot found webhook in Shopify. ERROR: {}".format(err))
        res = super(ShopifyWebhook, self).write(vals)
        return res

    def unlink(self):
        for record in self:
            if record.active_webhook:
                record.mk_instance_id.connection_to_shopify()
                existing_shopify_events = shopify.Webhook().find(topic=self.webhook_event)
                for shopify_events in existing_shopify_events:
                    shopify_event_dict = shopify_events.to_dict()
                    webhook_address = shopify_event_dict.get('address', '') or ''
                    if webhook_address == self.mk_instance_id.webhook_url:
                        try:
                            shopify_events.destroy()
                        except Exception as err:
                            _logger.error("SHOPIFY WEBHOOK UNLINK: Cannot found webhook in Shopify. ERROR: {}".format(err))
        res = super(ShopifyWebhook, self).unlink()
        return res

    def shopify_delete_webhook(self):
        self.active_webhook = False
        return True
