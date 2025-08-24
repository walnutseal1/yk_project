# import memory.memtools as mt
import json
import utils.auth as auth
import ipi.webtools as wt
import ipi.fstools
import time
a = ""
# mt.vector_memory_edit(label="another_example_vector_block", new_text="user's", old_text="ser's")

def test():
    time.sleep(2)
    print("\n\n")
    print(a)

# billy = mt.memory_search("what is the password")
# print(billy)

# bob = ipi.fstools.edit_file("C:/users/walnu/documents/stuff.txt", "", "testing")
# print(bob)
a = wt.navigate("https://example.com")
test()
a = wt.extract_text("h1")

test()

a = wt.navigate("https://www.saucedemo.com/")
test()
a= wt.type_text("#user-name", "standard_user")
test()
a = wt.type_text("#password", "secret_sauce")
test()
a = wt.click("#login-button")

test()
a = wt.navigate("https://the-internet.herokuapp.com/key_presses")
test()
a = wt.type_text("#target", "Test Input\n")  # \n simulates Enter
test()
a = wt.extract_text("#result")
test()






time.sleep(5)
