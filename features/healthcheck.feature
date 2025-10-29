Feature: API healthcheck
  As a client of the API
  I want to check the service root endpoint
  So that I know the API is up

  Scenario: Root endpoint returns welcome message
    When I GET "/"
    Then the response status code should be 200
    And the JSON response should contain key "message"
