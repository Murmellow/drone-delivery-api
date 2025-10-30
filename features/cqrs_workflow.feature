Feature: CQRS local workflow with outbox and command processing
  As a developer testing the CQRS pattern
  I want to verify that commands flow through the outbox to the local queue
  And that the command worker processes them correctly
  So that the system works without AWS credentials

  Scenario: Local CQRS workflow - direct processing via local queue
    Given CQRS mode is enabled with local queue
    And a location named "Warehouse A" at latitude 40.0 and longitude -74.0
    And a location named "Customer Home" at latitude 40.01 and longitude -74.01
    And a customer exists with first name "Alice", last name "Johnson", email "alice@example.com", phone "555-1000", address "100 Elm St", and location "Customer Home"
    And an item exists titled "Tablet" priced 299.99 with stock 50
    And a drone exists model "DJI-X700" serial "DRN-CQRS-001" payload 10.0 range 50.0 at location "Warehouse A"
    When I place an order for customer "alice@example.com" with items:
      | item_title | quantity |
      | Tablet     | 1        |
    And I start local workflow for drone "DRN-CQRS-001" with item "Tablet" quantity 1 weight 0.8
    Then after waiting 3 seconds the local queue should have processed messages
    And the drone "DRN-CQRS-001" should have cargo loaded
    And a delivery should exist for the last order
    And the delivery should be completed
    And the drone "DRN-CQRS-001" status should be "available"
    And the drone "DRN-CQRS-001" should have no cargo

  Scenario: CQRS command endpoint - enqueue delivery via outbox
    Given CQRS mode is enabled with local queue
    And a location named "Warehouse B" at latitude 41.0 and longitude -75.0
    And a location named "Downtown" at latitude 41.01 and longitude -75.01
    And a customer exists with first name "Bob", last name "Smith", email "bob@example.com", phone "555-2000", address "200 Oak Ave", and location "Downtown"
    And an item exists titled "Laptop" priced 899.99 with stock 20
    And a drone exists model "DJI-X800" serial "DRN-CQRS-002" payload 15.0 range 60.0 at location "Warehouse B"
    When I place an order for customer "bob@example.com" with items:
      | item_title | quantity |
      | Laptop     | 1        |
    And I load cargo onto drone "DRN-CQRS-002" with item "Laptop" quantity 1 weight 2.5
    And I request delivery creation via CQRS command for the last order using drone "DRN-CQRS-002"
    Then the CQRS command should be accepted
    And after waiting 2 seconds the outbox should have published messages
    And a delivery should exist for the last order with drone "DRN-CQRS-002"
