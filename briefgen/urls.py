from django.urls import path

from brief import views

urlpatterns = [
    path("", views.index, name="index"),
    path("styleguide", views.styleguide, name="styleguide"),
    path("api/brief", views.create_brief, name="create_brief"),
    path("api/brief/<str:public_id>", views.get_brief, name="get_brief"),
]
