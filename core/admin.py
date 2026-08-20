from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from files.models import ProcessedFile, UploadedFile
from workflows.models import Execution, Workflow, WorkflowOperation


class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "original_name", "file_type", "size", "rows_count", "created_at")
    list_filter = ("file_type",)
    search_fields = ("original_name", "user__email")


class ProcessedFileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "original_name", "source_name", "file_type", "rows_after", "created_at")
    list_filter = ("file_type",)
    search_fields = ("original_name", "source_name", "user__email")


class WorkflowOperationInline(admin.TabularInline):
    model = WorkflowOperation
    extra = 0


class WorkflowAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "name", "updated_at")
    inlines = [WorkflowOperationInline]


class ExecutionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "workflow", "status", "rows_before", "rows_after", "created_at")
    list_filter = ("status",)


admin.site.register(UploadedFile, UploadedFileAdmin)
admin.site.register(ProcessedFile, ProcessedFileAdmin)
admin.site.register(Workflow, WorkflowAdmin)
admin.site.register(Execution, ExecutionAdmin)

admin.site.unregister(User)
admin.site.register(User, UserAdmin)