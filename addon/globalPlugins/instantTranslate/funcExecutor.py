# Copyright (C) 2023 Cyrille Bougot
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

import NVDAObjects
from scriptHandler import script, executeScript
import keyboardHandler


def executeWithSpeakOnDemand(f, *args, **kwargs):
	"""Allows to execute a function forcing the on-demand mode for its execution.
	This may be useful for a functions that is scheduled by an on-demand scripts 
	to be run after the script execution has finished, e.g. using `core.callLater`.

	Parameters:
	f: function to execute.
	args: unnamed arguments to pass to the function.
	kwargs: keyword arguments to pass to the function.
	"""

	gesture = keyboardHandler.KeyboardInputGesture.fromName(' ')
	scriptableObject = _FuncExecutor(f, *args, **kwargs)
	return executeScript(scriptableObject.script_callFunWithOnDemand, gesture)


class _FuncExecutor(NVDAObjects.baseObject.ScriptableObject):
	"""A scriptable object allowing to run a function in an on-demand script.
	"""

	def __init__(self, f, *args, **kwargs):
		self.f = f
		self.args = args
		self.kwargs = kwargs

	@script(
		speakOnDemand=True,
	)
	def script_callFunWithOnDemand(self, gesture):
		return self.f(*self.args, **self.kwargs)
	