import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

from utils import Logging, PageNotLoadingError
from constants import DRIVER_PATH

class DriverWrapper:
    def __init__(self, max_trials, trial_wait_time):
        self.max_trials = max_trials
        self.trial_wait_time = trial_wait_time

    def _wrap_find_in_trials(self, find_method, element_to_find):
        for trial in range(self.max_trials):
            try:
                element = find_method(element_to_find)
                return element
            except:
                time.sleep(self.trial_wait_time)

        raise PageNotLoadingError(f'Driver could not find element {element_to_find}. ' +\
                                   'Either the element is not present, or the page has not loaded successfully.')


class Driver(DriverWrapper):
    """ Wrapper for the Selenium webdriver. Used to avoid crashes when page has not yet fully loaded or a popup has appeared
        that is blocking an element. Instead of crashing, the Driver will make 'max_trials' attempts to complete the command
        (e.g. to find an element by xpath or to click on a button)
    """
    __executable_path = DRIVER_PATH

    def __init__(self, logger=None, max_trials=3, trial_wait_time=4, driver_wait_time = 5):
        super().__init__(max_trials, trial_wait_time)
        self.logger = logger
        self.driver_wait_time = driver_wait_time

        self.__driver = webdriver.Firefox(executable_path=self.__executable_path)
        self.__driver.implicitly_wait(driver_wait_time)
        self.__driver_waiter = WebDriverWait(self.__driver, driver_wait_time)

    @property
    def page_source(self):
        #return self.__driver.page_source;
        return self.__driver.find_element_by_tag_name('html').get_attribute('innerHTML')

    @property
    def current_url(self):
        return self.__driver.current_url;
    
    def back(self): self.__driver.back();
    def start(self): self.__driver = webdriver.Firefox(executable_path=self.__executable_path);
    def close(self): self.__driver.close();
    def get(self, url): self.__driver.get(url);
    def refresh(self): self.__driver.refresh();

    def find_element_by_class_name(self, class_name):
        return DriverElement(self._wrap_find_in_trials(self.__driver.find_element_by_class_name, class_name), self.max_trials, self.trial_wait_time)
    def find_elements_by_class_name(self, class_name):
        return DriverElementGroup(self._wrap_find_in_trials(self.__driver.find_elements_by_class_name, class_name), self.max_trials, self.trial_wait_time)
    def find_element_by_xpath(self, xpath):
        return DriverElement(self._wrap_find_in_trials(self.__driver.find_element_by_xpath, xpath), self.max_trials, self.trial_wait_time)
    def find_elements_by_xpath(self, xpath):
        return DriverElementGroup(self._wrap_find_in_trials(self.__driver.find_elements_by_xpath, xpath), self.max_trials, self.trial_wait_time)

    def wait_until_visibility(self, by, content):
        for trial in range(self.max_trials):
            try:
                self.__driver_waiter.until(ec.visibility_of_element_located((by, content)))
                break
            except TimeoutException:
                time.sleep(self.trial_wait_time)
                
            error_msg = f'Could not find {by} \"{content}\" at page {self.current_url}'
            if self.logger is not None:
                self.logger.log_message(error_msg, Logging.ERROR)
            raise TimeoutException(error_msg)

class DriverElement(DriverWrapper):
    """ Wrapper for Selenium driver elements.
    """
    def __init__(self, element, max_trials, trial_wait_time):
        super().__init__(max_trials, trial_wait_time)
        self.__element = element

    def click(self):
        for trial in range(self.max_trials):
            try:
                self.__element.click()
                return
            except:
                time.sleep(self.trial_wait_time)

        raise PageNotLoadingError('Cannot click element - something may be obstructing it.')

    def get_attribute(self, attribute): return self.__element.get_attribute(attribute);

    def find_element_by_class_name(self, class_name):
        element = self._wrap_find_in_trials(self.__element.find_element_by_class_name, class_name)
        return DriverElement(element, self.max_trials, self.trial_wait_time)
    def find_elements_by_class_name(self, class_name):
        element = self._wrap_find_in_trials(self.__element.find_elements_by_class_name, class_name)
        return DriverElementGroup(element, self.max_trials, self.trial_wait_time)
    def find_element_by_xpath(self, xpath):
        element = self._wrap_find_in_trials(self.__element.find_element_by_xpath, xpath)
        return DriverElement(element, self.max_trials, self.trial_wait_time)
    def find_elements_by_xpath(self, xpath):
        element = self._wrap_find_in_trials(self.__element.find_elements_by_xpath, xpath)
        return DriverElementGroup(element, self.max_trials, self.trial_wait_time)

class DriverElementGroup(DriverWrapper):
    """ Wrapper for a collection of selenium driver elements. For example, when calling driver.find_elements_by_xpath
    """
    def __init__(self, elements, max_trials, trial_wait_time):
        super().__init__(max_trials, trial_wait_time)
        self.__elements = [DriverElement(element, max_trials, trial_wait_time) for element in elements]

    def __getitem__(self, key):
        return self.__elements[key]

    def __iter__(self):
        return iter(self.__elements)

    def __next__(self):
        return next(self.__elements)

    def __len__(self):
        return len(self.__elements)

