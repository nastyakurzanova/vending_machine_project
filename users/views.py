from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from quotes.models import TrainingTrade, RealTrade

def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('main:index')
    else:
        form = UserCreationForm()
    return render(request, 'users/register.html', {'form': form})

def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('main:index')
    else:
        form = AuthenticationForm()
    return render(request, 'users/login.html', {'form': form})

def user_logout(request):
    logout(request)
    return redirect('main:index')

@login_required
def profile(request):
    user = request.user
    training_trades_count = TrainingTrade.objects.filter(user=user).count()
    real_trades_count = RealTrade.objects.filter(user=user).count()
    context = {
        'user': user,
        'training_trades_count': training_trades_count,
        'real_trades_count': real_trades_count,
    }
    return render(request, 'users/profile.html', context)

@login_required
def delete_account(request):
    if request.method == 'POST':
        user = request.user
        logout(request)
        user.delete()
        messages.success(request, 'Ваш аккаунт был успешно удалён.')
        return redirect('main:index')
    return redirect('users:profile')