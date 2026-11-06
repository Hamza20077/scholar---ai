from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import StudyDocument


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")


class DeleteAccountForm(forms.Form):
    confirmation = forms.CharField(max_length=24, label="Type DELETE to confirm")
    password = forms.CharField(widget=forms.PasswordInput, label="Your current password")

    def clean_confirmation(self):
        value = self.cleaned_data["confirmation"].strip()
        if value != "DELETE":
            raise forms.ValidationError("Type DELETE exactly to confirm account removal.")
        return value


class UploadDocumentForm(forms.Form):
    title = forms.CharField(max_length=180, label="Document title")
    file = forms.FileField(label="PDF file")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        from django.conf import settings

        if upload.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f"File exceeds the {settings.MAX_UPLOAD_MB} MB upload limit.")
        if not upload.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Upload a PDF file.")
        return upload


class AskQuestionForm(forms.Form):
    question = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Ask a question about your selected notes…"}))
    documents = forms.ModelMultipleChoiceField(queryset=StudyDocument.objects.none(), widget=forms.CheckboxSelectMultiple, required=True)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["documents"].queryset = StudyDocument.objects.filter(owner=user)
