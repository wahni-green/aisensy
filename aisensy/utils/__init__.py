# Copyright (c) 2024, Wahni IT Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils.safe_exec import safe_eval
import requests


EVENT_MAPPING = {
    0: "Save",
    1: "Submit",
    2: "Cancel",
}

class AiSensy():
    def __init__(self, doc=None):
        self.settings = frappe.get_single("AiSensy Settings")
        self.enabled = self.settings.enabled
        self.valid_notifications = []
        self.destination = []
        self.params = []
        self.doc = doc
        self.context = doc.as_dict()
        self.is_success = True

    def is_enabled(self):
        return self.enabled

    def send_notification(self, event):
        if not self.is_enabled():
            return
        
        self.get_valid_notifications(event)
        if not self.valid_notifications:
            return

        frappe.msgprint(_("Sending WhatsApp notification for {0}").format(self.doc.name))
        for notification in self.valid_notifications:
            self.get_destination_and_params(notification)
            self._send_notification(notification.campaign, notification.send_pdf)

        if self.is_success:
            frappe.msgprint(_("WhatsApp notification sent successfully for {0}").format(self.doc.name))

    def get_valid_notifications(self, event):
        self.valid_notifications = []
        notifications = frappe.get_all(
            "AiSensy Notification",
            filters={"event": event, "enabled": 1, "document_type": self.doc.doctype},
            fields=["name", "condition", "campaign"]
        )

        for notification in notifications:
            if notification.condition:
                if not frappe.safe_eval(notification.condition, None, {"doc": self.doc}):
                    continue
            self.valid_notifications.append(
                frappe.get_doc("AiSensy Notification", notification)
            )

    def get_destination_and_params(self, notification_doc):
        self.destination = []
        self.params = []
        duplicate_nos = []
        for destination in notification_doc.destinations:
            data = {
                "number": safe_eval(destination.destination_no_field, None, self.context),
                "username": safe_eval(destination.destination_user, None, self.context),
            }
            if data["number"] in duplicate_nos:
                continue
            if data["number"] and data["username"]:
                duplicate_nos.append(data["number"])
                self.destination.append(data)

        if not self.destination:
            self.is_success = False
            frappe.msgprint(
                _("{0}: No destination number found for notification")
                .format(notification_doc.title)
            )

        for param in notification_doc.params:
            self.params.append(
                str(safe_eval(param.parameter_field, None, self.context))
            )

    def generate_media_url(self):
        from frappe.utils import get_url
        return "{0}/api/method/frappe.utils.print_format.download_pdf?doctype={1}&name={2}&key={3}".format(
            get_url(), self.doc.doctype, self.doc.name, self.doc.get_document_share_key()
        )

    def _send_notification(self, campaign, send_media=False):
        for destination in self.destination:
            try:
                payload = {
                    "apiKey": self.settings.get_password("api_key"),
                    "campaignName": campaign,
                    "destination": destination["number"],
                    "userName": destination["username"],
                    "templateParams": self.params,
                }
                if send_media:
                    payload["media"] = {}
                    payload["media"]["url"] = self.generate_media_url()
                    payload["media"]["filename"] = self.doc.name

                frappe.log_error("payload", str(payload))
                response = requests.post(self.settings.url, json=payload)
                if response.status_code != 200:
                    frappe.log_error(
                        title= f"Error sending notification",
                        message=str(response.json())
                    )
                response.raise_for_status()
            except Exception as e:
                self.is_success = False
                frappe.msgprint(
                    _("Error sending notification: {0}")
                    .format(e)
                )


def send_notification(doc, method):
    event = EVENT_MAPPING.get(doc.docstatus)
    if not event:
        return

    aisensy = AiSensy(doc)
    aisensy.send_notification(event)
