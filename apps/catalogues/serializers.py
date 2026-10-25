from django.utils import timezone
from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.customers.models import Customer
from apps.pricelists.models import PriceList
from apps.productcategories.models import ProductCategory
from apps.products.models import Product

from .models import Catalogue


class CatalogueSerializer(serializers.ModelSerializer):
    customer_id = WorkspaceRelatedField(Customer, source="customer", allow_null=True, required=False)
    customer_name = serializers.CharField(source="customer.name", read_only=True, default=None)
    price_list_id = WorkspaceRelatedField(PriceList, source="price_list", allow_null=True, required=False)
    price_list_name = serializers.CharField(source="price_list.name", read_only=True, default=None)
    category_ids = WorkspaceRelatedField(ProductCategory, source="categories", many=True, required=False)
    product_ids = WorkspaceRelatedField(Product, source="products", many=True, required=False)
    excluded_product_ids = WorkspaceRelatedField(Product, source="excluded_products", many=True, required=False)
    url = serializers.CharField(read_only=True)
    product_count = serializers.SerializerMethodField()
    quote_count = serializers.SerializerMethodField()
    is_open = serializers.SerializerMethodField()

    class Meta:
        model = Catalogue
        fields = ["id", "name", "intro", "customer_id", "customer_name", "price_list_id", "price_list_name", "category_ids", "product_ids",
                  "excluded_product_ids", "quote_mode", "show_prices", "show_stock", "expires_on", "is_active", "url", "view_count",
                  "last_viewed_at", "product_count", "quote_count", "is_open", "created_at"]
        read_only_fields = ["id", "customer_name", "price_list_name", "url", "view_count", "last_viewed_at", "product_count", "quote_count",
                            "is_open", "created_at"]

    def get_product_count(self, obj) -> int:
        from .services import products_of

        return products_of(obj).count()

    def get_quote_count(self, obj) -> int:
        return obj.quotations.count()

    def get_is_open(self, obj) -> bool:
        return obj.is_active and not (obj.expires_on and obj.expires_on < timezone.localdate())

    def validate(self, attrs):
        categories = attrs.get("categories", self.instance.categories.all() if self.instance else [])
        products = attrs.get("products", self.instance.products.all() if self.instance else [])
        if not list(categories) and not list(products):
            raise serializers.ValidationError({"category_ids": ["Choose at least one category or product."]})
        return attrs


class CatalogueItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    code = serializers.CharField()
    description = serializers.CharField()
    category = serializers.CharField()
    unit = serializers.CharField()
    image_url = serializers.CharField()
    price = serializers.CharField(allow_null=True)
    vat_percent = serializers.CharField()
    in_stock = serializers.BooleanField(allow_null=True)


class CatalogueBusinessSerializer(serializers.Serializer):
    name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.CharField()
    address = serializers.CharField()
    logo_url = serializers.CharField()
    currency = serializers.CharField()


class PublicCatalogueSerializer(serializers.Serializer):
    name = serializers.CharField()
    intro = serializers.CharField()
    business = CatalogueBusinessSerializer()
    customer_name = serializers.CharField(allow_null=True)
    show_prices = serializers.BooleanField()
    show_stock = serializers.BooleanField()
    reviews_first = serializers.BooleanField()
    expires_on = serializers.DateField(allow_null=True)
    pdf_available = serializers.BooleanField()
    items = CatalogueItemSerializer(many=True)


class CataloguePickSerializer(serializers.Serializer):
    product_id = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)


class CatalogueWishSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=200, allow_blank=True)  # blank rows are skipped
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, required=False, default=1)


class CatalogueQuoteRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    company = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=30)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = CataloguePickSerializer(many=True, required=False, default=list)
    wishes = CatalogueWishSerializer(many=True, required=False, default=list, help_text="Things the client couldn't find, in their own words")


class CatalogueQuoteLinkSerializer(serializers.Serializer):
    token = serializers.CharField()
    status = serializers.CharField()


class SharedQuoteLineSerializer(serializers.Serializer):
    description = serializers.CharField()
    quantity = serializers.CharField()
    unit = serializers.CharField()
    unit_price = serializers.CharField(allow_null=True)
    tax_rate_name = serializers.CharField(allow_null=True)
    total_amount = serializers.CharField(allow_null=True)


class SharedQuoteSerializer(serializers.Serializer):
    business = CatalogueBusinessSerializer()
    customer = serializers.DictField(child=serializers.CharField())
    number = serializers.CharField()
    status = serializers.CharField()
    ready = serializers.BooleanField()
    issue_date = serializers.DateField()
    valid_until = serializers.DateField()
    is_expired = serializers.BooleanField()
    currency = serializers.CharField()
    prices_include_tax = serializers.BooleanField()
    catalogue_token = serializers.CharField(allow_null=True)
    pdf_available = serializers.BooleanField()
    subtotal = serializers.CharField(allow_null=True)
    tax_total = serializers.CharField(allow_null=True)
    total = serializers.CharField(allow_null=True)
    lines = SharedQuoteLineSerializer(many=True)


class SharedQuoteAnswerSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["accept", "decline"])


class CatalogueAnalyticsTotalsSerializer(serializers.Serializer):
    catalogues = serializers.IntegerField()
    views = serializers.IntegerField()
    requests = serializers.IntegerField()
    accepted = serializers.IntegerField()
    requested_value = serializers.CharField()
    accepted_value = serializers.CharField()
    win_rate = serializers.FloatField()


class CatalogueAnalyticsRowSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    customer_name = serializers.CharField(allow_null=True)
    is_active = serializers.BooleanField()
    views = serializers.IntegerField()
    requests = serializers.IntegerField()
    accepted = serializers.IntegerField()
    requested_value = serializers.CharField()
    accepted_value = serializers.CharField()
    request_rate = serializers.FloatField()
    win_rate = serializers.FloatField()


class CatalogueTopProductSerializer(serializers.Serializer):
    product_id = serializers.CharField()
    name = serializers.CharField()
    times = serializers.IntegerField()
    quantity = serializers.CharField()
    value = serializers.CharField()


class CatalogueAnalyticsSerializer(serializers.Serializer):
    totals = CatalogueAnalyticsTotalsSerializer()
    catalogues = CatalogueAnalyticsRowSerializer(many=True)
    top_products = CatalogueTopProductSerializer(many=True)


class SendCatalogueSerializer(serializers.Serializer):
    to = serializers.ListField(child=serializers.EmailField(), min_length=1, max_length=10)
    message = serializers.CharField(max_length=4000)
