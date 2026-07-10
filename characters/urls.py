"""URL configuration for characters app."""

from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "characters"

urlpatterns = [
    # Auth
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path("register/pending/", views.register_pending, name="register_pending"),
    path(
        "register/confirm/<uidb64>/<token>/",
        views.register_confirm,
        name="register_confirm",
    ),
    path(
        "email-confirmation/resend/",
        views.resend_confirmation,
        name="resend_confirmation",
    ),
    path(
        "email-confirmation/",
        views.email_confirmation_status,
        name="email_confirmation_status",
    ),
    # Password reset. Django's stock views default their success_url to
    # non-namespaced names, which don't resolve under app_name = "characters",
    # so each redirecting step overrides it (the confirm view does so in
    # ConfirmingPasswordResetConfirmView, which also marks the email confirmed).
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            success_url=reverse_lazy("characters:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        views.ConfirmingPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    # User profiles
    path("users/<str:username>/", views.user_profile, name="user_profile"),
    # Character list
    path("", views.character_list, name="character_list"),
    path("character/create/", views.character_create, name="character_create"),
    # Character sheet
    path("character/<int:pk>/", views.character_sheet, name="character_sheet"),
    # Per-user layout preferences (not character-scoped)
    path("layout/order/<str:scope>/", views.save_order, name="save_order"),
    # HTMX field editing
    path(
        "character/<int:pk>/edit-field/",
        views.edit_field,
        name="edit_field",
    ),
    path(
        "character/<int:pk>/update-field/",
        views.update_field,
        name="update_field",
    ),
    # Items
    path("character/<int:pk>/add-item/", views.add_item, name="add_item"),
    path("character/<int:pk>/add-money/", views.add_money, name="add_money"),
    path("item/<int:item_id>/delete/", views.delete_item, name="delete_item"),
    path(
        "item/<int:item_id>/edit-field/", views.edit_item_field, name="edit_item_field"
    ),
    path(
        "item/<int:item_id>/update-field/",
        views.update_item_field,
        name="update_item_field",
    ),
    path(
        "item/<int:container_id>/put-in-container/",
        views.put_in_container,
        name="put_in_container",
    ),
    path(
        "item/<int:item_id>/remove-from-container/",
        views.remove_from_container,
        name="remove_from_container",
    ),
    # Conditions
    path(
        "character/<int:pk>/add-condition/",
        views.add_condition,
        name="add_condition",
    ),
    path(
        "condition/<int:condition_id>/delete/",
        views.delete_condition,
        name="delete_condition",
    ),
    # Hit dice
    path(
        "character/<int:pk>/add-hit-die/",
        views.add_hit_die,
        name="add_hit_die",
    ),
    path(
        "hit-die/<int:hit_die_id>/delete/",
        views.delete_hit_die,
        name="delete_hit_die",
    ),
    path(
        "character/<int:pk>/add-bonus-hp/",
        views.add_bonus_hp,
        name="add_bonus_hp",
    ),
    path(
        "bonus-hp/<int:bonus_hp_id>/delete/",
        views.delete_bonus_hp,
        name="delete_bonus_hp",
    ),
    # Spells
    path(
        "character/<int:pk>/add-spell/",
        views.add_spell,
        name="add_spell",
    ),
    path(
        "spell/<int:spell_id>/delete/",
        views.delete_spell,
        name="delete_spell",
    ),
    path(
        "spell/<int:spell_id>/toggle-memorized/",
        views.toggle_spell_memorized,
        name="toggle_spell_memorized",
    ),
    # Section refreshes
    path(
        "character/<int:pk>/section/<str:section>/",
        views.section_refresh,
        name="section_refresh",
    ),
    # Wiki export
    path(
        "character/<int:pk>/wiki-export/",
        views.wiki_export,
        name="wiki_export",
    ),
    # Sage knowledge
    path(
        "character/<int:pk>/sage/chosen-field/form/",
        views.sage_chosen_field_form,
        name="sage_chosen_field_form",
    ),
    path(
        "character/<int:pk>/sage/chosen-field/",
        views.sage_chosen_field,
        name="sage_chosen_field",
    ),
    path(
        "character/<int:pk>/sage/study-options/",
        views.sage_study_options,
        name="sage_study_options",
    ),
    path(
        "character/<int:pk>/sage/study/<int:study_pk>/points/",
        views.sage_study_points,
        name="sage_study_points",
    ),
    path(
        "character/<int:pk>/sage/study/add/",
        views.sage_study_add,
        name="sage_study_add",
    ),
    # Feedback
    path("feedback/", views.feedback, name="feedback"),
]
