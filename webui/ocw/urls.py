from django.urls import path
from . import views

urlpatterns = [
    path('', views.FilteredInstanceTableView.as_view(), name='instances'),
    path('instances', views.FilteredInstanceTableView.as_view(), name='instances'),
    path('update', views.update, name='update'),
    path('delete/<str:key_id>', views.delete, name='delete_instance'),
]
