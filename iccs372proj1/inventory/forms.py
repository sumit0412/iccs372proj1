from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Category, InventoryItem
from django.core.exceptions import ValidationError


class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class InventoryItemForm(forms.ModelForm):
    category = forms.ModelChoiceField(queryset=Category.objects.all(), initial=0)

    class Meta:
        model = InventoryItem
        fields = ['name', 'quantity', 'category']


from django import forms
from .models import Reservation


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ['start_time', 'end_time', 'purpose']
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'purpose': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        room_key = cleaned_data.get('room_key')

        if start_time and end_time and room_key:
            # Get the instance being updated (if any)
            instance = getattr(self, 'instance', None)

            # Check for conflicts excluding the current reservation
            conflicts = Reservation.objects.filter(
                room_key=room_key,
                status='confirmed',
                start_time__lt=end_time,
                end_time__gt=start_time
            )

            if instance and instance.pk:
                conflicts = conflicts.exclude(pk=instance.pk)

            if conflicts.exists():
                raise ValidationError('This time slot conflicts with an existing reservation.')

        return cleaned_data
