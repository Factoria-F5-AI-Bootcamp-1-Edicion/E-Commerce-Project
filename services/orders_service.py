from fastapi import HTTPException
from datetime import datetime
from config.db_config import session
from models.models import Order,Customer, Product_Order
from services.products_service import get_product
from models.models import Product
from schemas.dto import order_dto,DTO_product

#Variable global que contabiliza numero de order 
NUMBER_ORDER = 1

def inc_number():
  global NUMBER_ORDER
  NUMBER_ORDER +=1

def get_orders():
  orders= []
  item = None
  # Obtiene orders de tabla product_orders
  orders_list = session.query(Order).filter(Order.id_order==Product_Order.order_id).all()
  for order in orders_list:
    #Obtiene los datos de cada pedido (order,productos y cliente)
    item= get_order_byid(order.id_order)
    orders.append(item.copy())
  return orders

  """_summary_: Cada order o pedido contiene datos del pedido + los productos incluidos + cliente
  """
def get_order_byid(id):
  try:
    if session.query(Order).filter(Order.id_order == id) !=None: 
      item = {"order":None,"data":None,"customer":None,"payment_method":None}
      order=session.query(Order).filter(Order.id_order==id).first()
      item["order"]= order
      products =session.query(Product).filter(Product_Order.product_id == Product.sku).filter(Product_Order.order_id== id).all()
      item["data"]= get_data_products(products,order)
      item["customer"] = session.query(Customer).filter(Customer.id_customer==order.customer_id).first()
    else:
      raise HTTPException(404,detail=f'Order with id {id} not found')
  except:
      session.rollback()
      session.close()
      raise HTTPException(500, detail='Transaction Server Error')
  return item

def get_data_products(products,order):
  items = []
  try :
    for item in products:
      row= session.query(Product_Order).filter(Product_Order.order_id==order.id_order).filter(Product_Order.product_id==item.sku).first()
      item = [DTO_product(get_product(item.sku),True),{"quantity": row.qty},{"payment":row.payment}]
      items.append(item.copy())
  except:
      session.rollback()
      session.close()
      raise HTTPException(500, detail='Transaction Server Error')
  return items

def create_order(order):
    product_ok = verify_product_bysku(order.products)
    result= {"order": None, "products":None, "customer":None}
    try:
      if product_ok["status"]==True:
        date =datetime.now()
        ammount_total,products_detail = calculate_total(order.products)
        customer = create_customer(order.customer)
        last_order = session.query(Order).order_by(Order.id_order.desc()).first()
        if last_order == None:
          # Uso de variable global (No declarada en esta funcion)
          global NUMBER_ORDER
          new_id = NUMBER_ORDER
        else:
          new_id = last_order.id_order + 1
        new_order = Order(new_id,customer,ammount_total,order.shipping_address,order.order_address,order.order_email,date,"NEW")
        # Agregar order        
        session.add(new_order)
        session.commit()
        insert_details(new_id,order.products,order.payment_method)
        #Ejecutar transaccion (Podria ejecutar previamente varias operaciones y al hacer commit se ejecutarian como una sola unidad sobre la base de datos) --> Actualizao BBDDD
        session.commit()
        inc_number()
        # Mi respuesta va a contener : pedido, detalles de productos pedidos y datos del cliente
        result["order"]=new_order
        result["products"]=products_detail
        result["customer"]=get_customer(customer.id_customer)
        session.refresh(new_order)
    except:
          # En caso que no se pueda ejecutar la insercion, hago rollback de la trasaccion y lanzo un HttpException
          # Borrar cliente, y order si hay algun error 
          session.rollback()
          session.close()
          raise HTTPException(404, detail='Transaction Error order')
    return result,product_ok

def insert_details(id_order,products,payment):
    for product in products:
        product= dict(product)
        detail=Product_Order(id_order,product["sku"],product["quantity"],payment)
        session.add(detail)
    
def create_customer(customer):
    respuesta = None
    obj = session.query(Customer).order_by(Customer.id_customer.desc()).first()
    if obj == None:
      new_id = 1
    else:
      new_id =obj.id_customer +1
    if verify_customer(customer.email) == True :
      respuesta = session.query(Customer).filter(Customer.email == customer.email).first()
    else:
      new_customer = Customer(new_id,customer.full_name,customer.email,customer.billing_address,customer.default_shipping_address,customer.zip_code,customer.country,customer.phone)
     # Ejecuto transaccion para agregar el cliente 
      try:
          # Agregar cliente
          session.add(new_customer)    
          #Ejecutar transaccion con varias operaciones y al hacer commit se ejecutarian como una sola unidad sobre la base de datos)
          session.commit()
          respuesta = new_customer
          session.refresh(new_customer)
          respuesta = get_customer(id)
          session.close()
      except: 
            # En caso que no se pueda ejecutar la insercion, hago rollback de la trasaccion y lanzo un HttpException
            session.rollback()
            session.close()
            raise HTTPException(404, detail='Transaction Error customer')
    # Recupera de la BBDD el cliente creado y lo retorna como respuesta
    return respuesta

def verify_customer(email):
    customer_exist = False
    if session.query(Customer).filter(Customer.email == email).first() != None:
      customer_exist = True
    return customer_exist


        
# Verificacion de existencia de producto y si hay stock suficiente segun la cantidad pedida
def verify_product_bysku(products):
    result = {"status": True,"msj":""}
    for product in products:
        response = session.query(Product).filter(Product.sku == product.sku).first()
        if response == None:
          result["status"] =False
          result["msg"] ="Product sku not found"
          break
        if response.qty < product.quantity:
           result["status"] =False
           result["msg"] ="quantity unavailable in store`s stock"
           break
        if product.quantity < 1:
           result["status"] =False
           result["msg"] ="Minimum quantity of Product's order must be one unity"
    return result

def calculate_total(products):
    total_ammount = 0.0
    products_detail =[]
    product_detail={"product": None, "quantity": 0, "total":0.0}
    for product in products:
        product= dict(product)
        producto = session.query(Product).filter(Product.sku == product["sku"]).first()
        total = product["quantity"] * producto.price
        product_detail["product"] = DTO_product(get_product(producto.sku),False)
        product_detail["quantity"] = product["quantity"]
        product_detail["total"] = total
        total_ammount += total
        products_detail.append(product_detail.copy())
        update_stock(product["sku"],product["quantity"])
        producto = None
        
    return total_ammount,products_detail

  
def update_stock(sku,qty_request):
  try:
    new_stock= session.query(Product).filter(Product.sku==sku).first().qty -qty_request
    session.query(Product).filter(Product.sku==sku).update({"qty" : new_stock})
    session.commit()
  except: 
            # En caso que no se pueda ejecutar la insercion, hago rollback de la trasaccion y lanzo un HttpException
            session.rollback()
            session.close()
            raise HTTPException(404, detail='Transaction Error updating stock')

  

def get_customer(id):
  result = session.query(Customer).filter(Customer.id_customer == id).first()
  return result

