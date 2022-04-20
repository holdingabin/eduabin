from decouple import config
import stripe
import json

from decimal import Decimal
from users.models import User
from .models import Payment, PaymentIntent
from rest_framework.views import APIView
from courses.models import Course
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

stripe_api_key=config("STRIPE_APIKEY")
endpoint_secret="whsec_59aa4d3bf0f83a2aedfe97e70422bcd61eda8f95b88992d2550ab1897441cbb1"
stripe.api_key=stripe_api_key

class PaymentHandler(APIView):
    permission_classes=[IsAuthenticated]
    def post(self, request):
        if request.body:
            body=json.loads(request.body)
            if body and len(body):
                course_line_items=[]
                cart_course=[]
                for item in body:
                    try:
                        course=Course.objects.get(course_uuid=item)
                        line_item={
                            "price_data":{
                                "currency": "usd",
                                "unit_amount": int(course.price*100),
                                "product_data":{
                                    "name": course.title,
                                }
                            },
                            "quantity":1
                        }

                        course_line_items.append(line_item)
                        cart_course.append(course)

                    except Course.DoesNotExist:
                        return Response(status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response(status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        
        checkout_session=stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=course_line_items,
            mode="payment",
            success_url="http://localhost:3000/",
            cancel_url="http://localhost:3000/",
        )

        intent=PaymentIntent.objects.create(
            payment_intent_id=checkout_session.payment_intent,
            checkout_id=checkout_session.id,
            user=User.objects.get(id=1)
        )

        intent.course.add(*cart_course)

        return Response({"url":checkout_session.url})

class WebHook(APIView):
    def post(self, request):
        payload=request.body
        sig_header=request.META["HTTP_STRIPE_SIGNATURE"]

        event=None

        try:
            event=stripe.Webhook.construct_event(
                payload=payload, sig_header=sig_header, secret=endpoint_secret
            )

        except:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        
        if event["type"]=="checkout.session.completed":
            session=event["data"]["object"]

            try:
                intent=PaymentIntent.objects.get(checkout_id=session.id, payment_intent_id=session.payment_intent)

            except PaymentIntent.DoesNotExist:
                return Response(status=status.HTTP_400_BAD_REQUEST)
            
            Payment.objects.create(
                payment_intent=intent,
                total_amount=Decimal(session.amount_total/100)
            )

            intent.user.paid_courses.add(*intent.course.all())

            return Response(status=200)
        
        else:
            return Response(status=status.HTTP_400_BAD_REQUEST)