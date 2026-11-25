from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .invite import reset_link, send_invite

admin.site.site_header = "Catalog Manager"
admin.site.site_title = admin.site.site_header
admin.site.index_title = admin.site.site_header


class InviteForm(forms.ModelForm):
    email = forms.EmailField()  # an invite needs somewhere to go

    class Meta:
        model = get_user_model()
        fields = ("username", "email", "groups")


admin.site.unregister(get_user_model())


@admin.register(get_user_model())
class CatalogUserAdmin(UserAdmin):
    """Users are created without a password: the person gets an emailed
    one-time link and chooses their own, so no password is ever shared."""

    add_form = InviteForm
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("username", "email", "groups")}),)
    actions = ["send_invite_action"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.set_unusable_password()
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        self._invite(request, obj)
        return super().response_add(request, obj, post_url_continue)

    @admin.action(description="Send password-set email")
    def send_invite_action(self, request, queryset):
        for user in queryset:
            self._invite(request, user)

    def _invite(self, request, user):
        if send_invite(request, user):
            messages.success(request, "Password-set email sent to %s." % (user.email or user.username))
        else:
            messages.warning(
                request,
                "No email could be sent. Send this link to %s yourself: %s"
                % (user.email or user.username, reset_link(request, user)),
            )
