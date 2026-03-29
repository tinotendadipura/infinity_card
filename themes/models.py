from django.db import models


class Theme(models.Model):
    name = models.CharField(max_length=50)
    primary_color = models.CharField(max_length=7, default='#2EC4B6')
    secondary_color = models.CharField(max_length=7, default='#6B2FA0')
    background_color = models.CharField(max_length=7, default='#FFFFFF')
    text_color = models.CharField(max_length=7, default='#1E293B')
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
