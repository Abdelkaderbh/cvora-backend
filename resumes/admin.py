from django.contrib import admin

from resumes.models import CV, Analysis, User

admin.site.register(User)
admin.site.register(CV)
admin.site.register(Analysis)
