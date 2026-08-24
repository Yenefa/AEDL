*** Settings ***
Suite Setup                   Setup
Test Teardown                 Test Teardown
Resource                      ${RENODEKEYWORDS}

*** Test Cases ***
Should Load STM32G0 Platform Description
    Execute Command           mach create
    ${load}=  Execute Command  machine LoadPlatformDescription @platforms/cpus/stm32g0.repl
    Should Not Contain        ${load}    couldn't
    Should Not Contain        ${load}    error

Should Instantiate G0 Peripheral Models
    Execute Command           mach create
    Execute Command           machine LoadPlatformDescription @platforms/cpus/stm32g0.repl
    ${periph}=  Execute Command  peripherals
    Should Contain            ${periph}    adc
    Should Contain            ${periph}    dma1
    Should Contain            ${periph}    nvic
