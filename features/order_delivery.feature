Feature: Place order and assign drone for delivery
  As a client of the API
  I want to place an order
  And assign a drone to deliver it
  So that the customer receives the items

  Scenario: Place order, assign a drone, and check delivery status
    Given a location named "Warehouse A" at latitude 40.0 and longitude -74.0
    And a location named "Customer Home" at latitude 40.01 and longitude -74.01
    And a customer exists with first name "John", last name "Doe", email "john@example.com", phone "123", address "123 Main", and location "Customer Home"
    And an item exists titled "Widget" priced 19.99 with stock 100
    And a drone exists model "DJI-X500" serial "DRN-001" payload 5.0 range 30.0 at location "Warehouse A"
    When I place an order for customer "john@example.com" with items:
      | item_title | quantity |
      | Widget     | 2        |
    Then the order status should be "pending"
    And I load cargo onto drone "DRN-001" with item 1 quantity 2 weight 2.0
    When I create a delivery for the last order using drone "DRN-001"
    Then I can fetch the delivery and it should exist

  Scenario: Process multiple orders sequentially with a single drone
    Given a location named "Warehouse A" at latitude 40.0 and longitude -74.0
    And a location named "Customer Home" at latitude 40.01 and longitude -74.01
    And a location named "Office" at latitude 40.02 and longitude -74.02
    And a customer exists with first name "John", last name "Doe", email "john@example.com", phone "123", address "123 Main", and location "Customer Home"
    And a customer exists with first name "Jane", last name "Smith", email "jane@example.com", phone "456", address "456 Oak", and location "Office"
    And an item exists titled "Gadget" priced 49.99 with stock 100
    And a drone exists model "DJI-X500" serial "DRN-001" payload 5.0 range 30.0 at location "Warehouse A"
    When I place an order for customer "john@example.com" with items:
      | item_title | quantity |
      | Gadget     | 1        |
    And I load cargo onto drone "DRN-001" with item 1 quantity 1 weight 1.0
    And I create a delivery for the last order using drone "DRN-001"
    When I place an order for customer "jane@example.com" with items:
      | item_title | quantity |
      | Gadget     | 2        |
    When I attempt to create a delivery for the last order using drone "DRN-001"
    Then the last response should be 400 with message "Drone is not available"
    And I complete the last delivery
    And I move the drone "DRN-001" to location "Warehouse A"
    And I load cargo onto drone "DRN-001" with item 1 quantity 2 weight 2.0
    And I create a delivery for the last order using drone "DRN-001"
    Then I can fetch the delivery and it should exist

  Scenario: Change drone status manually
    Given a location named "Warehouse A" at latitude 40.0 and longitude -74.0
    And a drone exists model "DJI-X500" serial "DRN-001" payload 5.0 range 30.0 at location "Warehouse A"
    When I set the drone "DRN-001" status to "maintenance"
    Then the drone "DRN-001" status should be "maintenance"
    When I set the drone "DRN-001" status to "available"
    Then the drone "DRN-001" status should be "available"

  Scenario: Restocking workflow - load cargo before delivery
    Given a location named "Warehouse A" at latitude 40.0 and longitude -74.0
    And a location named "Customer Home" at latitude 40.01 and longitude -74.01
    And a customer exists with first name "Alice", last name "Brown", email "alice@example.com", phone "789", address "789 Pine", and location "Customer Home"
    And an item exists titled "Tablet" priced 299.99 with stock 50
    And a drone exists model "DJI-X500" serial "DRN-002" payload 5.0 range 30.0 at location "Warehouse A"
    When I place an order for customer "alice@example.com" with items:
      | item_title | quantity |
      | Tablet     | 1        |
    When I attempt to create a delivery for the last order using drone "DRN-002"
    Then the last response should be 400 with message "Drone is not available"
    When I load cargo onto drone "DRN-002" with item 1 quantity 1 weight 2.5
    Then the drone "DRN-002" status should be "loaded"
    And the drone "DRN-002" should have cargo weight 2.5
    When I create a delivery for the last order using drone "DRN-002"
    Then I can fetch the delivery and it should exist
    And the drone "DRN-002" status should be "in_delivery"
    When I complete the last delivery
    Then the drone "DRN-002" status should be "available"
    And the drone "DRN-002" should have cargo weight 0.0

  Scenario: Load multiple items and check payload capacity
    Given a location named "Warehouse A" at latitude 40.0 and longitude -74.0
    And a drone exists model "DJI-X500" serial "DRN-003" payload 5.0 range 30.0 at location "Warehouse A"
    When I load cargo onto drone "DRN-003" with item 1 quantity 2 weight 2.0
    Then the drone "DRN-003" should have cargo weight 2.0
    When I load cargo onto drone "DRN-003" with item 2 quantity 1 weight 2.5
    Then the drone "DRN-003" should have cargo weight 4.5
    When I attempt to load cargo onto drone "DRN-003" with item 3 quantity 1 weight 1.0
    Then the last response should be 400 with message containing "Exceeds payload capacity"

  Scenario: Unload cargo manually
    Given a location named "Warehouse A" at latitude 40.0 and longitude -74.0
    And a drone exists model "DJI-X500" serial "DRN-004" payload 5.0 range 30.0 at location "Warehouse A"
    When I load cargo onto drone "DRN-004" with item 1 quantity 3 weight 3.0
    Then the drone "DRN-004" should have cargo weight 3.0
    When I unload cargo from drone "DRN-004" with item 1 quantity 2
    Then the drone "DRN-004" should have cargo weight 1.0
    When I unload cargo from drone "DRN-004" with item 1 quantity 1
    Then the drone "DRN-004" status should be "available"
    And the drone "DRN-004" should have cargo weight 0.0
