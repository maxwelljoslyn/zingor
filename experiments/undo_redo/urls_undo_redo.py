"""Undo/redo URL patterns, extracted from characters/urls.py."""

from django.urls import path

from . import views

urlpatterns = [
    path("character/<int:pk>/undo/", views.undo, name="undo"),
    path("character/<int:pk>/redo/", views.redo, name="redo"),
]
