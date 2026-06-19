from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    voter_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    is_voter = models.BooleanField(default=True)
    is_admin_user = models.BooleanField(default=False)
    is_active_voter = models.BooleanField(default=True)
    phone_number = models.CharField(max_length=20, blank=True)

    def save(self, *args, **kwargs):
        if not self.voter_id and self.is_voter:
            super().save(*args, **kwargs)
            self.voter_id = f"VTR-{self.pk:06d}"
            User.objects.filter(pk=self.pk).update(voter_id=self.voter_id)
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.voter_id or 'admin'})"


class VoterRegister(models.Model):
    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20)
    secret_code = models.CharField(max_length=20, unique=True)
    is_used = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    registered_user = models.OneToOneField(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='voter_register'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} - {self.secret_code}"


class Election(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('closed', 'Closed'),
    ]
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Candidate(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name='candidates')
    full_name = models.CharField(max_length=200)
    party = models.CharField(max_length=100, blank=True)
    bio = models.TextField(blank=True)
    photo = models.ImageField(upload_to='candidates/', blank=True, null=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'full_name']

    def __str__(self):
        return f"{self.full_name} ({self.election.title})"


class Vote(models.Model):
    voter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='votes')
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name='votes')
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='votes')
    cast_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('voter', 'election')

    def __str__(self):
        return f"{self.voter.username} voted in {self.election.title}"


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('login_success', 'Login Success'),
        ('login_failed', 'Login Failed'),
        ('vote_cast', 'Vote Cast'),
        ('voter_registered', 'Voter Registered'),
        ('voter_deactivated', 'Voter Deactivated'),
        ('voter_activated', 'Voter Activated'),
        ('election_created', 'Election Created'),
        ('election_activated', 'Election Activated'),
        ('election_closed', 'Election Closed'),
        ('bulk_upload', 'Bulk Upload'),
    ]
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    username = models.CharField(max_length=150, blank=True)
    ip_address = models.CharField(max_length=50, blank=True)
    details = models.TextField(blank=True)
    election = models.ForeignKey(Election, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} - {self.username} - {self.timestamp}"