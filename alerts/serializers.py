import json

from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Alert


class AlertNamesField(serializers.Field):
    """
    Accepts alert names in any of these forms:
      - JSON body:        ["person", "vehicle"]
      - multipart repeat: alert_names=person & alert_names=vehicle
      - JSON string:      '["person","vehicle"]'
      - comma string:     'person,vehicle'
    """

    def get_value(self, dictionary):
        # multipart / QueryDict -> use getlist so repeated keys work
        if hasattr(dictionary, 'getlist'):
            values = dictionary.getlist(self.field_name)
            if not values:
                return serializers.empty
            return values if len(values) > 1 else values[0]
        return dictionary.get(self.field_name, serializers.empty)

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = data.strip()
            if data.startswith('['):
                try:
                    data = json.loads(data)
                except ValueError:
                    raise serializers.ValidationError('Invalid JSON list.')
            else:
                data = [x for x in data.split(',')]
        if not isinstance(data, (list, tuple)):
            raise serializers.ValidationError('Must be a list of names.')
        names = [str(x).strip().lower() for x in data if str(x).strip()]
        if not names:
            raise serializers.ValidationError('At least one alert name is required.')
        return names

    def to_representation(self, value):
        return value


class AlertSerializer(serializers.ModelSerializer):
    alert_names = AlertNamesField()

    class Meta:
        model = Alert
        fields = ['id', 'image', 'alert_names', 'camera_no', 'alert_time', 'created_date']
        read_only_fields = ['id', 'created_date']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ['username', 'password', 'email']

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
