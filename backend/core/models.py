import uuid

from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission


class User(AbstractUser):
    class Meta:
        db_table = "user"

    # the uuid is what we'll use in the unsubscribe link
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    groups = models.ManyToManyField(Group, related_name="accounts_user_groups")
    user_permissions = models.ManyToManyField(
        Permission,
        related_name="accounts_user_permissions",
    )

class StudySession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

class Flashcard(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    study_session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name='flashcards')
    question = models.TextField()
    answer = models.TextField()

class FlashcardStudy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    flashcard = models.ForeignKey(Flashcard, on_delete=models.CASCADE, related_name='studies')
    study_session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name='card_studies')
    knowledge_level = models.IntegerField(choices=[(1, 'Well Known'), (2, 'Somewhat Known'), (3, 'Not Known')])
    studied_at = models.DateTimeField(auto_now_add=True)
