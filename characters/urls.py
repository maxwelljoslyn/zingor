"""URL configuration for characters app."""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "characters"

urlpatterns = [
    # Auth
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    # Character list
    path("", views.character_list, name="character_list"),
    path("character/create/", views.character_create, name="character_create"),
    # Character sheet
    path("character/<int:pk>/", views.character_sheet, name="character_sheet"),
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
    # Undo/Redo
    path("character/<int:pk>/undo/", views.undo, name="undo"),
    path("character/<int:pk>/redo/", views.redo, name="redo"),
    # Items
    path("character/<int:pk>/add-item/", views.add_item, name="add_item"),
    path("item/<int:item_id>/delete/", views.delete_item, name="delete_item"),
    path("item/<int:item_id>/edit-field/", views.edit_item_field, name="edit_item_field"),
    path("item/<int:item_id>/update-field/", views.update_item_field, name="update_item_field"),
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
]
