from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, UpdateView, DeleteView, ListView
from django.views.generic import TemplateView, View
from django.utils import timezone
from django.http import Http404
from django.core.exceptions import ValidationError

from .forms import UserRegisterForm, InventoryItemForm, ReservationForm
from .models import InventoryItem, Category, LabRoom

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


class SearchSuggestions(LoginRequiredMixin, View):
    def get(self, request):
        query = request.GET.get("q", "")
        if query:
            items = InventoryItem.objects.filter(name__icontains=query, user=request.user).values("name")[:5]
            return JsonResponse(list(items), safe=False)
        return JsonResponse([], safe=False)


class RoomCalendarView(LoginRequiredMixin, View):
    def get(self, request):
        context = {
            'lab_rooms': settings.LAB_ROOMS,
            'timezone': settings.TIMEZONE,
            'default_calendar_id': settings.LAB_ROOMS['room1']['calendar_id']
        }
        return render(request, 'inventory/room_calendar.html', context)


class CreateReservationView(LoginRequiredMixin, View):
    def get_lab_room(self, room_key):
        if room_key not in settings.LAB_ROOMS:
            raise Http404("Lab room not found")
        room_data = settings.LAB_ROOMS[room_key]
        return {
            'name': room_data['name'],
            'calendar_id': room_data['calendar_id'],
            'key': room_key
        }

    def get(self, request, room_key):
        room = self.get_lab_room(room_key)
        form = ReservationForm()
        return render(request, 'inventory/create_reservation.html', {
            'form': form,
            'room': room
        })

    def post(self, request, room_key):
        room = self.get_lab_room(room_key)
        form = ReservationForm(request.POST)

        if form.is_valid():
            reservation = form.save(commit=False)
            reservation.user = request.user
            reservation.room_key = room_key
            reservation.calendar_id = room['calendar_id']
            reservation.status = 'confirmed'  # Set status to confirmed

            try:
                reservation.save()
                messages.success(request, "Reservation created successfully")
                return redirect('room-calendar')
            except ValidationError as e:
                messages.error(request, str(e))
                return render(request, 'inventory/create_reservation.html', {
                    'form': form,
                    'room': room
                })
            except Exception as e:
                messages.error(request, f"Error creating reservation: {str(e)}")
                return render(request, 'inventory/create_reservation.html', {
                    'form': form,
                    'room': room
                })

        return render(request, 'inventory/create_reservation.html', {
            'form': form,
            'room': room
        })