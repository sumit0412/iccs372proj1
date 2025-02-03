from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import Http404
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.views.generic import TemplateView, View

from .forms import UserRegisterForm, InventoryItemForm, ReservationForm
from .models import InventoryItem, Category, Reservation

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
            'timezone': settings.TIME_ZONE,
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
        form = ReservationForm(initial={'room_key': room_key})  # Add initial value
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


class UpdateReservationView(LoginRequiredMixin, View):
    def get_object(self):
        return get_object_or_404(Reservation, pk=self.kwargs['pk'], user=self.request.user)

    def get_room_name(self, room_key):
        return settings.LAB_ROOMS.get(room_key, {}).get('name', 'Unknown Room')

    def get(self, request, *args, **kwargs):
        reservation = self.get_object()
        form = ReservationForm(instance=reservation)
        return render(request, 'inventory/update_reservation.html', {
            'form': form,
            'reservation': reservation,
            'room_name': self.get_room_name(reservation.room_key)  # Add this
        })

    def post(self, request, *args, **kwargs):
        reservation = self.get_object()
        form = ReservationForm(request.POST, instance=reservation)
        if form.is_valid():
            form.save()
            messages.success(request, 'Reservation updated successfully.')
            return redirect('reservation_list')  # or wherever you want to redirect
        return render(request, 'inventory/update_reservation.html', {
            'form': form,
            'reservation': reservation
        })


class DeleteReservationView(LoginRequiredMixin, View):
    def get_object(self):
        return get_object_or_404(Reservation, pk=self.kwargs['pk'], user=self.request.user)

    def post(self, request, *args, **kwargs):
        reservation = self.get_object()
        reservation.delete()
        messages.success(request, 'Reservation deleted successfully.')
        return redirect('reservation_list')

    def get(self, request, *args, **kwargs):
        reservation = self.get_object()
        return render(request, 'inventory/delete_reservation.html', {
            'reservation': reservation
        })


class ReservationListView(LoginRequiredMixin, ListView):
    model = Reservation
    template_name = 'inventory/reservation_list.html'
    context_object_name = 'reservations'
    paginate_by = 10

    def get_queryset(self):
        # Get base queryset
        queryset = Reservation.objects.filter(user=self.request.user)

        # Add status filter
        status = self.request.GET.get('status')
        if status in ['confirmed', 'pending', 'cancelled']:
            queryset = queryset.filter(status=status)

        # Filter out past reservations if requested
        show_past = self.request.GET.get('show_past') == 'true'
        if not show_past:
            queryset = queryset.filter(end_time__gte=timezone.localtime())

        return queryset.order_by('-start_time')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add all necessary context variables
        context.update({
            'lab_rooms': settings.LAB_ROOMS,
            'status': self.request.GET.get('status', ''),
            'show_past': self.request.GET.get('show_past', 'false'),
            'now': timezone.localtime(),
            'is_paginated': self.paginate_by and self.get_queryset().count() > self.paginate_by,
        })

        # Add page range for better pagination display
        if context['is_paginated']:
            page = context['page_obj']
            paginator = context['paginator']

            # Calculate page range to display
            ADJACENT_PAGES = 2
            page_range = range(
                max(1, page.number - ADJACENT_PAGES),
                min(paginator.num_pages + 1, page.number + ADJACENT_PAGES + 1)
            )
            context['page_range'] = page_range

        return context
