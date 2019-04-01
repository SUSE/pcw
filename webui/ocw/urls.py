from django.urls import path
from . import views

urlpatterns = [
    path('', views.FilteredInstanceTableView.as_view(), name='instances'),
    path('instances', views.FilteredInstanceTableView.as_view(), name='instances'),
    path('cron', views.cron, name='cron'),
    path('update', views.update, name='update'),
    path('update/status', views.update_status, name='update_status'),
    path('delete/<str:key_id>', views.delete, name='delete_instance'),
]
