from django.contrib import admin
from django.urls import path, include, reverse_lazy
from .views import (
    Index, SignUpView, Dashboard, AddItem, EditItem, DeleteItem, SearchSuggestions,
    ScheduleView, GoogleCalendarInitView, GoogleCalendarRedirectView
)
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', Index.as_view(), name='index'),
    path('dashboard/', Dashboard.as_view(), name='dashboard'),
    path('add-item/', AddItem.as_view(), name='add-item'),
    path('edit-item/<int:pk>', EditItem.as_view(), name='edit-item'),
    path('delete-item/<int:pk>', DeleteItem.as_view(), name='delete-item'),
    path('signup/', SignUpView.as_view(), name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='inventory/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(template_name='inventory/logout.html'), name='logout'),
    path('search_suggestions/', SearchSuggestions.as_view(), name='search_suggestions'),

    # New paths for scheduling and Google Calendar OAuth
    path('schedule/', ScheduleView.as_view(), name='schedule'),
    path('google_calendar/init/', GoogleCalendarInitView.as_view(), name='google_calendar_init'),
    path('google_calendar/redirect/', GoogleCalendarRedirectView.as_view(), name='google_calendar_redirect'),
]