"""Seed the demo database with realistic, faker-generated e-commerce data.

The data is deliberately *interesting*: it contains baked-in anomalies so that LLM
summaries have something to discover.

  * Electronics has an abnormally high refund rate (~25% vs ~3% elsewhere).
  * One flagship product is permanently out of stock while still active.
  * One calendar month has a ~3x spike in order volume.

The command is idempotent: running it on an already-seeded database is a no-op unless
``--reset`` is passed, which wipes the store tables and reseeds from scratch.

Usage:
    python demo/manage.py seed_data
    python demo/manage.py seed_data --reset
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker

from store.models import Category, Order, OrderItem, Product

SEED = 42

# Category name -> (price range, sample product nouns).
CATEGORIES = {
    "Electronics": (
        (49, 1499),
        ["Headphones", "Laptop", "Smartphone", "Monitor", "Keyboard", "Webcam"],
    ),
    "Books": ((8, 45), ["Novel", "Cookbook", "Biography", "Textbook", "Guide", "Anthology"]),
    "Clothing": ((15, 180), ["T-Shirt", "Jacket", "Jeans", "Sweater", "Dress", "Sneakers"]),
    "Home & Kitchen": (
        (12, 350),
        ["Blender", "Cookware Set", "Lamp", "Knife Set", "Kettle", "Towels"],
    ),
    "Sports & Outdoors": (
        (20, 600),
        ["Tent", "Yoga Mat", "Dumbbells", "Backpack", "Bicycle", "Water Bottle"],
    ),
    "Toys & Games": (
        (10, 120),
        ["Board Game", "Puzzle", "Action Figure", "Building Set", "Plush Toy", "Card Game"],
    ),
    "Beauty": ((6, 90), ["Serum", "Lipstick", "Shampoo", "Perfume", "Moisturizer", "Face Mask"]),
    "Office Supplies": (
        (4, 75),
        ["Notebook", "Pen Set", "Stapler", "Desk Organizer", "Planner", "Whiteboard"],
    ),
}

# Roughly realistic status distribution for "normal" categories.
NORMAL_STATUSES = (
    [Order.Status.DELIVERED] * 55
    + [Order.Status.SHIPPED] * 12
    + [Order.Status.PAID] * 12
    + [Order.Status.PENDING] * 10
    + [Order.Status.CANCELLED] * 8
    + [Order.Status.REFUNDED] * 3
)


class Command(BaseCommand):
    help = "Seed the demo store with realistic fake data (with baked-in anomalies)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Wipe existing store data before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        fake = Faker()
        Faker.seed(SEED)
        random.seed(SEED)

        if options["reset"]:
            self.stdout.write("Resetting store data...")
            OrderItem.objects.all().delete()
            Order.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()

        if Order.objects.exists():
            self.stdout.write(
                self.style.WARNING(
                    "Store already contains data. Use --reset to wipe and reseed. Skipping."
                )
            )
            return

        categories = self._seed_categories()
        products = self._seed_products(fake, categories)
        self._seed_orders(fake, products)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Category.objects.count()} categories, "
                f"{Product.objects.count()} products, "
                f"{Order.objects.count()} orders, "
                f"{OrderItem.objects.count()} order items."
            )
        )

    def _seed_categories(self):
        categories = {}
        for name in CATEGORIES:
            categories[name] = Category.objects.create(
                name=name, description=f"{name} products available in the demo store."
            )
        return categories

    def _seed_products(self, fake, categories):
        products = []
        for name, (price_range, nouns) in CATEGORIES.items():
            category = categories[name]
            low, high = price_range
            for _ in range(10):  # 8 categories x 10 = 80 products
                noun = random.choice(nouns)
                product = Product(
                    name=f"{fake.unique.word().capitalize()} {noun}",
                    category=category,
                    price=Decimal(random.randint(low, high)) + Decimal("0.99"),
                    stock=random.randint(0, 500),
                    is_active=random.random() > 0.05,
                )
                products.append(product)

        # Anomaly: one flagship Electronics product is permanently out of stock.
        products[0].name = "Flagship Pro Headphones"
        products[0].stock = 0
        products[0].is_active = True

        Product.objects.bulk_create(products)
        fake.unique.clear()
        return list(Product.objects.all())

    def _seed_orders(self, fake, products):
        now = timezone.now()
        electronics_ids = {p.id for p in products if p.category.name == "Electronics"}
        # Anomaly: pick one month in the past year to spike order volume.
        spike_month_offset = random.randint(2, 9)

        orders = []
        for _ in range(300):
            month_offset = random.randint(0, 11)
            # Triple the chance of landing in the spike month.
            if random.random() < 0.5:
                month_offset = spike_month_offset
            created = now - timedelta(
                days=month_offset * 30 + random.randint(0, 29),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            orders.append(
                Order(
                    status=random.choice(NORMAL_STATUSES),
                    total=Decimal("0.00"),  # filled in after items are created
                    customer_email=fake.email(),
                    created_at=created,
                )
            )
        Order.objects.bulk_create(orders)
        orders = list(Order.objects.all())

        items = []
        for order in orders:
            item_count = random.randint(1, 3)  # avg ~2 -> ~600 items
            chosen = random.sample(products, item_count)
            order_total = Decimal("0.00")
            order_is_electronics = False
            for product in chosen:
                quantity = random.randint(1, 4)
                items.append(
                    OrderItem(
                        order=order,
                        product=product,
                        quantity=quantity,
                        unit_price=product.price,
                    )
                )
                order_total += product.price * quantity
                if product.id in electronics_ids:
                    order_is_electronics = True

            order.total = order_total
            # Anomaly: Electronics-heavy orders get refunded far more often.
            if order_is_electronics and random.random() < 0.25:
                order.status = Order.Status.REFUNDED

        OrderItem.objects.bulk_create(items)
        Order.objects.bulk_update(orders, ["total", "status"])
