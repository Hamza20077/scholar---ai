from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("healthz/", views.health, name="health"),
    path("privacy/", views.privacy, name="privacy"),
    path("service-worker.js", views.service_worker, name="service_worker"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="study/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/signup/", views.signup, name="signup"),
    path("", views.dashboard, name="dashboard"),
    path("documents/upload/", views.upload_document, name="upload_document"),
    path("ask/", views.ask_question, name="ask_question"),
    path("documents/<int:document_id>/generate/<str:kind>/", views.generate_artifact, name="generate_artifact"),
    path("documents/<int:document_id>/delete/", views.delete_document, name="delete_document"),
    path("materials/<int:artifact_id>/", views.artifact_detail, name="artifact_detail"),
    path("materials/<int:artifact_id>/delete/", views.delete_artifact, name="delete_artifact"),
    path("account/delete/", views.delete_account, name="delete_account"),
]
