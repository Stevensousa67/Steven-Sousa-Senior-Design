from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from formtools.wizard.views import SessionWizardView
from .forms import SignupForm, UserForm, ProfileForm, ProfileSelectForm, ExperienceFormSet, ProjectFormSet, \
    ReferenceFormSet
from .models import User, Profile, Experience, Project, Reference
from django.contrib.auth.views import LoginView


# Custom Login View
class CustomLoginView(LoginView):
    template_name = 'candidate/login.html'

    def get_success_url(self):
        user = self.request.user
        if not user.first_name:
            return reverse('candidate:edit_user')
        return reverse('jobs:jobs_list')


# Signup View
def signup(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = User.objects.create_user(username=email, email=email, password=password)
            login(request, user)
            return redirect('candidate:edit_user')
    else:
        form = SignupForm()
    return render(request, 'candidate/signup.html', {'form': form})


# Custom Logout View
def logout_view(request):
    logout(request)
    return redirect('jobs:index')


# View profiles
@login_required
def view_profiles(request):
    profiles = Profile.objects.filter(user=request.user)

    if request.method == 'POST':
        profile_id = request.POST.get('profile_id')
        if profile_id:
            profile = get_object_or_404(Profile, id=profile_id, user=request.user)  # Ensure user owns the profile
            try:
                profile.delete()
                messages.success(request, "Profile deleted successfully.")
            except Exception as e:
                messages.error(request, f"Error deleting profile: {str(e)}")
            return redirect('candidate:view_profiles')

    return render(request, 'candidate/view_profiles.html', {'profiles': profiles})


# Profile Create View (kept for standalone use if needed)
@login_required
def create_profile(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            return redirect('candidate:edit_user')
    else:
        form = ProfileForm()
    return render(request, 'candidate/edit_user.html', {'form': form})


# Edit User and Profile Wizard
class EditUserWizard(SessionWizardView):
    form_list = [
        ('user', UserForm),
        ('profile_select', ProfileSelectForm),
        ('experience', ExperienceFormSet),
        ('projects', ProjectFormSet),
        ('references', ReferenceFormSet),
    ]
    template_name = 'candidate/edit_user.html'

    def get_form_prefix(self, step, form=None):
        prefixes = {
            'user': 'user',
            'profile_select': 'profile_select',
            'experience': 'experiences',
            'projects': 'projects',
            'references': 'references',
        }
        return prefixes[step]

    def get_form_instance(self, step):
        if step == 'user':
            return self.request.user
        return None

    def get_form_initial(self, step):
        if step == 'user':
            user = self.request.user
            return {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'phone': user.phone,
                'website': user.website,
                'address': user.address,
                'education': user.education,
                'major': user.major,
                'skills': user.skills,
                'courses': user.courses,
            }
        return None

    def _get_formset_class(self, step):
        formset_map = {
            'experience': ExperienceFormSet,
            'projects': ProjectFormSet,
            'references': ReferenceFormSet,
        }
        return formset_map.get(step)

    def _get_formset(self, step, data, files, profile=None):
        formset_class = self._get_formset_class(step)
        if not formset_class:
            return None
        prefix = step if step != 'experience' else 'experiences'
        kwargs = {'data': data, 'files': files, 'prefix': prefix}
        if profile:
            kwargs['instance'] = profile
        return formset_class(**kwargs)

    def _get_profile_for_step(self):
        """Retrieve the profile based on profile_select step data."""
        profile_data = self.get_cleaned_data_for_step('profile_select')
        if profile_data:
            profile_option = profile_data.get('profile_option')
            if profile_option == 'existing' and profile_data.get('existing_profile'):
                try:
                    return Profile.objects.get(
                        id=profile_data['existing_profile'].id,  # Ensure we get the ID
                        user=self.request.user
                    )
                except Profile.DoesNotExist:
                    print(
                        f"Profile with id {profile_data['existing_profile'].id} not found for user {self.request.user}")
                    return None
            elif profile_option == 'new' and profile_data.get('new_profile_name'):
                profile, _ = Profile.objects.get_or_create(
                    user=self.request.user,
                    profile_name=profile_data['new_profile_name'].strip()
                )
                return profile
        return None

    def _handle_formset_step(self, step, data, files):
        """Handle formset creation for experience, projects, and references steps."""
        profile = self._get_profile_for_step()
        return self._get_formset(step, data, files, profile)

    def get_form(self, step=None, data=None, files=None):
        """Get the form for the current step with reduced complexity."""
        step = step or self.steps.current
        prefix = self.get_form_prefix(step)
        print(f"Step: {step}, Prefix: {prefix}")  # Debug

        try:
            if step == 'profile_select':
                return ProfileSelectForm(data=data, files=files, user=self.request.user, prefix=prefix)
            elif step in ['experience', 'projects', 'references']:
                return self._handle_formset_step(step, data, files)
            return super().get_form(step, data, files)
        except Exception as e:
            print(f"Error in get_form for step {step}: {str(e)}")
            raise

    def process_step(self, form):
        if self.steps.current == 'profile_select':
            cleaned_data = form.cleaned_data
            profile_option = cleaned_data.get('profile_option')

            if profile_option == 'new':
                new_profile_name = cleaned_data.get('new_profile_name', '').strip()
                if new_profile_name:
                    profile, created = Profile.objects.get_or_create(
                        user=self.request.user,
                        profile_name=new_profile_name
                    )
                    # Store the ID in storage, leave cleaned_data as is
                    self.storage.set_step_data(self.steps.current, {
                        'profile_select-existing_profile': str(profile.id),
                        'profile_select-profile_option': 'new',
                    })
                else:
                    form.add_error('new_profile_name', "Please enter a new profile name.")
            elif profile_option == 'existing':
                if not cleaned_data.get('existing_profile'):
                    form.add_error('existing_profile', "Please select an existing profile.")
        return self.get_form_step_data(form)

    def get_form_kwargs(self, step):
        kwargs = super().get_form_kwargs(step)
        if step in ['experience', 'projects', 'references']:
            profile = self._get_profile_for_step()
            if profile:
                if step == 'experience':
                    kwargs['queryset'] = Experience.objects.filter(profile=profile)
                elif step == 'projects':
                    kwargs['queryset'] = Project.objects.filter(profile=profile)
                elif step == 'references':
                    kwargs['queryset'] = Reference.objects.filter(profile=profile)
        return kwargs

    def done(self, form_list, **kwargs):
        # Extract data from all steps
        user_form = form_list[0]  # UserForm (first step)
        profile_select_form = form_list[1]  # ProfileSelectForm (second step)
        experience_formset = form_list[2]  # ExperienceFormSet
        projects_formset = form_list[3]  # ProjectFormSet
        references_formset = form_list[4]  # ReferenceFormSet

        # Save user data
        user = user_form.save(commit=False)
        user.save()

        # Determine if we're creating a new profile or using an existing one
        profile_data = profile_select_form.cleaned_data
        profile_option = profile_data.get('profile_option')

        if profile_option == 'existing':
            profile = profile_data.get('existing_profile')  # This is a Profile object
            if not profile:
                raise ValueError("No existing profile selected.")
        else:  # profile_option == 'new'
            profile_name = profile_data.get('new_profile_name')
            profile, created = Profile.objects.get_or_create(
                profile_name=profile_name,
                user=self.request.user
            )

        # Save formsets with the profile
        experience_formset.instance = profile
        experience_formset.save()

        projects_formset.instance = profile
        projects_formset.save()

        references_formset.instance = profile
        references_formset.save()

        messages.success(self.request, "Profile saved successfully.")
        return redirect('jobs:jobs_list')

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form=form, **kwargs)
        context['step_name'] = self.steps.current
        return context


edit_user = login_required(EditUserWizard.as_view())
