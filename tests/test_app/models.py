from dirtyfields import DirtyFieldsMixin
from django.db import models


class AuditedThing(DirtyFieldsMixin, models.Model):
    name = models.CharField(max_length=120)

    class Meta:
        app_label = "tests_test_app"


class Tag(models.Model):
    label = models.CharField(max_length=50)

    class Meta:
        app_label = "tests_test_app"


class AuditedBasket(models.Model):
    name = models.CharField(max_length=120)
    tags = models.ManyToManyField(Tag, related_name="baskets")

    class Meta:
        app_label = "tests_test_app"
