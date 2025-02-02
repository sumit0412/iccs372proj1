from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView, View, CreateView, UpdateView, DeleteView
from django.contrib.auth import authenticate, login
from django.contrib.auth.mixins import LoginRequiredMixin
from .forms import UserRegisterForm, InventoryItemForm
from .models import InventoryItem, Category
from django.views.generic import TemplateView, View
import os
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery

from django.conf import settings
LOW_QUANTITY = settings.LOW_QUANTITY

from django.contrib import messages

class Index(TemplateView):
    template_name = 'inventory/index.html'

class Dashboard(LoginRequiredMixin, View):
    def get(self, request):
        search_query = request.GET.get('q', '')  # Get the search query from the URL
        quantity_filter = request.GET.get('quantity_filter', '')
        category_filter = request.GET.get('category_filter', '')

        items = InventoryItem.objects.filter(user=self.request.user.id).order_by('id')

        # Apply search functionality
        if search_query:
            items = items.filter(name__icontains=search_query)

        # Apply category filter if selected
        if category_filter:
            items = items.filter(category_id=category_filter)

        # Apply quantity filter if selected
        if quantity_filter == 'high_to_low':
            items = items.order_by('-quantity')
        elif quantity_filter == 'low_to_high':
            items = items.order_by('quantity')

        # Highlight low stock items
        low_inventory = InventoryItem.objects.filter(
            user=self.request.user.id,
            quantity__lte=LOW_QUANTITY
        )

        if low_inventory.count() > 0:
            if low_inventory.count() > 1:
                messages.error(request, f'{low_inventory.count()} items have low inventory')
            else:
                messages.error(request, f'{low_inventory.count()} item has low inventory')

        low_inventory_ids = InventoryItem.objects.filter(
            user=self.request.user.id,
            quantity__lte=LOW_QUANTITY
        ).values_list('id', flat=True)

        # Get all categories for the category filter dropdown
        categories = Category.objects.all()

        return render(
            request,
            'inventory/dashboard.html',
            {
                'items': items,
                'low_inventory_ids': low_inventory_ids,
                'categories': categories,
                'search': search_query,
                'quantity_filter': quantity_filter,
                'category_filter': category_filter,
            }
        )



class SignUpView(View):
    def get(self, request):
        form = UserRegisterForm()
        return render(request, 'inventory/signup.html', {'form': form})

    def post(self, request):
        form = UserRegisterForm(request.POST)

        if form.is_valid():
            form.save()
            user = authenticate(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password1']
            )

            login(request, user)
            return redirect('index')

        return render(request, 'inventory/signup.html', {'form': form})

class AddItem(LoginRequiredMixin, CreateView):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = 'inventory/item_form.html'
    success_url = reverse_lazy('dashboard')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        return context

    def form_valid(self, form):
        if form.cleaned_data['quantity'] < 0:
            messages.error(self.request, "Quantity cannot be negative.")
            return self.form_invalid(form)  # Prevents saving the item

        form.instance.user = self.request.user
        return super().form_valid(form)

class EditItem(LoginRequiredMixin, UpdateView):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = 'inventory/item_form.html'
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        if form.cleaned_data['quantity'] < 0:
            messages.error(self.request, "Quantity cannot be negative.")
            return self.form_invalid(form)  # Prevents saving the item

        form.instance.user = self.request.user
        return super().form_valid(form)


class DeleteItem(LoginRequiredMixin, DeleteView):
    model = InventoryItem
    template_name = 'inventory/delete_item.html'
    success_url = reverse_lazy('dashboard')
    context_object_name = 'item'

class SearchSuggestions(View):
    def get(self, request):
        query = request.GET.get("q", "")
        if query:
            items = InventoryItem.objects.filter(name__icontains=query, user=request.user).values("name")[:5]
            return JsonResponse(list(items), safe=False)
        return JsonResponse([], safe=False)

# Define the required scopes for Google Calendar API (adjust scopes as needed)
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
# Optionally, you can add more scopes if needed (like calendar.events)

# Utility function to build the Google Calendar service
def build_calendar_service(request):
    if 'credentials' not in request.session:
        return None
    credentials = google.oauth2.credentials.Credentials(**request.session['credentials'])
    service = googleapiclient.discovery.build('calendar', 'v3', credentials=credentials)
    return service

class ScheduleView(LoginRequiredMixin, TemplateView):
    template_name = 'inventory/schedule.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        service = build_calendar_service(self.request)
        events = []
        if service:
            # Example: Retrieve the upcoming 10 events from the primary calendar
            try:
                events_result = service.events().list(
                    calendarId='primary',  # Or use a specific calendar ID for lab rooms
                    maxResults=10,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                events = events_result.get('items', [])
            except Exception as e:
                messages.error(self.request, f"Error accessing Google Calendar: {e}")
        context['events'] = events
        return context

class GoogleCalendarInitView(LoginRequiredMixin, View):
    """
    Initiates the OAuth2 flow with Google.
    """
    def get(self, request, *args, **kwargs):
        # Create the flow instance from the client secrets file.
        # Ensure that you have a file named 'client_secret.json' in your BASE_DIR.
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            os.path.join(settings.BASE_DIR, 'client_secret.json'),
            scopes=SCOPES
        )
        # Set the redirect URI for the OAuth2 callback.
        flow.redirect_uri = request.build_absolute_uri(reverse('google_calendar_redirect'))
        # Generate the authorization URL.
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        # Save the state in the session so that the callback can verify the auth flow.
        request.session['state'] = state
        return redirect(authorization_url)

class GoogleCalendarRedirectView(LoginRequiredMixin, View):
    """
    Handles the OAuth2 callback from Google.
    """
    def get(self, request, *args, **kwargs):
        state = request.session.get('state')
        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            os.path.join(settings.BASE_DIR, 'client_secret.json'),
            scopes=SCOPES,
            state=state
        )
        flow.redirect_uri = request.build_absolute_uri(reverse('google_calendar_redirect'))
        # Use the full URL to fetch the token.
        authorization_response = request.build_absolute_uri()
        try:
            flow.fetch_token(authorization_response=authorization_response)
        except Exception as e:
            messages.error(request, f"OAuth token fetch failed: {e}")
            return redirect('schedule')
        credentials = flow.credentials
        # Save the credentials in the session.
        request.session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        messages.success(request, "Google Calendar successfully connected!")
        return redirect('schedule')