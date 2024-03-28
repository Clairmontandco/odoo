# -*- coding: utf-8 -*-
{
    "name": "Joint Calendar",
    "version": "15.0.1.2.2",
    "category": "Extra Tools",
    "author": "faOtools",
    "website": "https://faotools.com/apps/15.0/joint-calendar-603",
    "license": "Other proprietary",
    "application": True,
    "installable": True,
    "auto_install": False,
    "depends": [
        "calendar",
        "mail"
    ],
    "data": [
        "security/security.xml",
        "views/event_rule.xml",
        "views/joint_calendar.xml",
        "views/joint_event.xml",
        "views/menu.xml",
        "data/cron.xml",
        "data/data.xml",
        "security/ir.model.access.csv"
    ],
    "assets": {
        "web.assets_backend": [
                "joint_calendar/static/src/js/joint_calendar_view.js",
                "joint_calendar/static/src/js/joint_calendar_notification.js"
        ]
},
    "demo": [
        
    ],
    "external_dependencies": {},
    "summary": "The tool to combine different Odoo events in a few configurable super calendars. Shared calendar. Common calendar. Merged calendar",
    "description": """For the full details look at static/description/index.html
* Features * 
- Super calendars for any business area
- Flexible rules to merge Odoo documents
- Multi companies compatibility
- &lt;i class=&#34;fa fa-tasks&#34;&gt; &lt;/i&gt; Combine events on Odoo Enterprise Gantt view
#odootools_proprietary""",
    "images": [
        "static/description/main.png"
    ],
    "price": "66.0",
    "currency": "EUR",
    "live_test_url": "https://faotools.com/my/tickets/newticket?&url_app_id=27&ticket_version=15.0&url_type_id=3",
}