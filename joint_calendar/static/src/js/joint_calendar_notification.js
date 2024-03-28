/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { ConnectionLostError } from "@web/core/network/rpc_service";
import { registry } from "@web/core/registry";

/*
* Implemented based on standard Odoo calendar notifications
*/
export const jointCalendarNotification = {
    dependencies: ["action", "notification", "rpc"],

    start(env, { action, notification, rpc }) {
        let calendarNotifJointTimeouts = {};
        let nextJointCalendarNotifTimeout = null;
        const displayedJointNotifications = new Set();
        env.bus.on("WEB_CLIENT_READY", null, async () => {
            const legacyEnv = owl.Component.env;
            legacyEnv.services.bus_service.onNotification(this, (notifications) => {
                for (const { payload, type } of notifications) {
                    if (type === "joint.event") {
                        displayJointCalendarNotification(payload);
                    }
                }
            });
            legacyEnv.services.bus_service.startPolling();
            getNextJointCalendarNotif();
        });

        function displayJointCalendarNotification(notifications) {
            let lastNotifTimer = 0;
            browser.clearTimeout(nextJointCalendarNotifTimeout);
            Object.values(calendarNotifJointTimeouts).forEach((notif) => browser.clearTimeout(notif));
            calendarNotifJointTimeouts = {};
            notifications.forEach(function (notif) {
                const key = notif.event_id + "," + notif.alarm_id;
                if (displayedJointNotifications.has(key)) {
                    return;
                }
                calendarNotifJointTimeouts[key] = browser.setTimeout(function () {
                    const notificationRemove = notification.add(notif.message, {
                        title: notif.title,
                        type: "warning",
                        sticky: true,
                        onClose: () => {
                            displayedJointNotifications.delete(key);
                        },
                        buttons: [
                            {
                                name: env._t("OK"),
                                primary: true,
                                onClick: async () => {
                                    await rpc("/calendar/notify_ack");
                                    notificationRemove();
                                },
                            },
                            {
                                name: env._t("Details"),
                                onClick: async () => {
                                    const action_id = await rpc(
                                        "joint_calendar/event/get/action",
                                        {"event_id": notif.event_id}, { silent: true }
                                    )
                                    await action.doAction(action_id);
                                    await rpc("/calendar/notify_ack");
                                    notificationRemove();
                                },
                            },
                            {
                                name: env._t("Snooze"),
                                onClick: () => {
                                    notificationRemove();
                                },
                            },
                        ],
                    });
                    displayedJointNotifications.add(key);
                }, notif.timer * 1000);
                lastNotifTimer = Math.max(lastNotifTimer, notif.timer);
            });

            if (lastNotifTimer > 0) {
                nextJointCalendarNotifTimeout = browser.setTimeout(
                    getNextJointCalendarNotif,
                    lastNotifTimer * 1000
                );
            }
        }

        async function getNextJointCalendarNotif() {
            try {
                const result = await rpc("/joint_calendar/notify", {}, { silent: true });
                displayJointCalendarNotification(result);
            } catch (error) {
                if (!(error instanceof ConnectionLostError)) {
                    throw error;
                }
            }
        }
    },
};

registry.category("services").add("jointCalendarNotification", jointCalendarNotification);
